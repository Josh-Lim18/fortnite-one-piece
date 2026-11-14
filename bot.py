"""Tight-aggressive Hold'em bot that profiles each seat and shifts its thresholds to exploit it.

One file, standard library only: the tournament sandbox loads nothing else.
"""
import base64
import gc
import math
import operator
import random
import struct
import time
from bisect import bisect_left, bisect_right

# Every tunable number lives here so tools/tune.py can search them.
PARAMS = {
    # Share of hands opened when nobody has raised, by players still to act behind.
    "open": {1: 0.40, 2: 0.42, 3: 0.28, 4: 0.22, 5: 0.17, 6: 0.14, 7: 0.12},
    "open_bb": 3.0,            # open-raise size in big blinds, plus one per limper
    "iso_raise": 0.12,         # big blind raises limpers with this share of hands
    "threebet_r": 0.30,        # re-raise when our hand is in this top share of the raiser's range
    "call_r": 0.85,            # call a raise when in this top share of the raiser's range
    "call_cap": 0.22,          # ...but never wider than this share of all hands
    "big_bet": 0.40,           # a bet this share of the starting stack counts as a shove
    "setmine_cost": 0.05,      # call with any pair when it costs at most this share of the stack
    "value": 0.62,             # bet when equity is above this
    "big_value": 0.80,         # bet big / raise when equity is above this
    "bet_frac": 0.66,          # the one postflop bet size, as a share of the pot, for value and bluffs alike
    "size_jitter": 0.10,       # every chosen raise size is scaled by a random factor within this share
    "mix_band": 0.03,          # within this distance of a threshold, mix the two actions with a sliding chance
    "call_margin": 0.06,       # equity needed beyond pot odds against a constant bettor
    "passive_margin": 0.16,    # extra equity needed against a seat that rarely bets
    "prior_value_share": 0.40, # prior share of our bluff spots in which we hold a value bet; bluffs make calling us break-even
    "risk": 0.0,               # added to every stack-off threshold; raise it to chase variance
    "prior_hands": 12.0,       # how many hands of "average player" each seat's stats start with
    "prior_vpip": 0.30,
    "prior_pfr": 0.15,
    "prior_shove": 0.03,
    "prior_aggr": 0.30,
    "allin_margin": 0.03,      # call a preflop all-in with equity this far above the pot odds
    # Layer 2 and the layer 3 picker.
    "profile": True,           # off: layer 2 reads nothing per seat, only population rates
    "temper": 0.05,            # weight of each observation in layer 2's type posterior
    "picker": True,            # off: play base only
    "pick_margin": 0.05,       # a skill is played only when its price beats base's by this share of the pot
    "pick_temp": 0.02,         # softmax temperature over option prices, as a share of the pot
    "value_edge": 0.12,        # preflop, base is unpriced: a value shove must gain this share of the raise when called
    "z_conf": 1.0,             # a read's confidence is its mean less this many spreads over layer 2's type blend
    "plan_trust": 0.9,         # chips the multi-street plan wins count at this share for each street after this one
    "light_prior": 3.0,        # hands of prior behind the direct all-in and bet-when-checked-to counts
    "prior_barrel": 0.35,      # prior chance a seat bets when checked to
    "track_n": 6,              # a skill keeps its last this many predicted-versus-observed responses per seat
    "track_min": 3,            # ...and needs this many before it can be switched off by them
    "diverge": 0.35,           # switch a skill off for a seat when its predictions overshoot by this much on average
    "track_hands": 150,        # misses older than this many hands are forgotten, so a skill can retry
    # Each skill turns on for a seat when its confidence reaches _on and off when it drops below _off.
    "value_shove_on": 0.45, "value_shove_off": 0.35,  # lower-bound chance the seat calls a stack-off
    "value_plan_on": 0.50, "value_plan_off": 0.40,    # lower-bound chance it calls the plan's first bet
    "bluff_on": 0.55, "bluff_off": 0.45,              # lower-bound chance it folds to our bet
    "call_shover_on": 0.20, "call_shover_off": 0.12,  # lower-bound share of hands it goes all in
    "barreller_on": 0.65, "barreller_off": 0.55,      # lower-bound chance it bets when checked to
    "equity_net": True,        # postflop equity from the network in equity_net/ instead of the Monte Carlo
    "trials": 60,              # Monte Carlo rollouts per postflop decision
    "decision_ms": 1.5,        # stop rolling out after this long
    "round_budget_s": 3.0,     # own thinking time after which rollouts are cut to a quarter
}

RANKS = "23456789TJQKA"
SUITS = "cdhs"
ORDER = (
    "AA KK QQ JJ TT 99 AKs 88 AQs AKo AJs AQo KQs ATs KJs 77 AJo KTs QJs A9s ATo KQo 66 A8s KJo K9s "
    "A9o A7s QTs A5s JTs A4s QJo KTo Q9s A6s QTo A8o K8s K9o 55 J9s A5o Q9o JTo A7o Q8s K6s T9s A6o "
    "A3s K7s K8o A2s A4o J8s T8s K5s 44 A3o 98s T9o Q7s J9o K6o K3s Q5s A2o J7s Q8o K4s T7s K7o K5o "
    "J8o Q6s K2s Q4s 87s Q7o K4o T8o 98o 97s Q3s 33 Q2s J5s T6s J7o J6s J3s 96s Q6o Q5o T7o J4s K3o "
    "87o 86s 22 76s 97o K2o 95s 85s Q4o 75s T5s J2s T4s J6o T3s Q3o 94s 96o Q2o 65s J5o J4o T6o 76o "
    "86o 92s 53s T2s 64s J3o 84s 54s 74s 85o 93s T4o 75o T5o 95o 65o 73s J2o 82s 83s 63s 43s 54o 64o "
    "72s 42s T2o 94o 52s T3o 74o 62s 32s 93o 92o 84o 53o 63o 43o 83o 82o 73o 42o 52o 62o 72o 32o"
)

# Upper triangle (i < j) of all-in equity of ORDER[i] against ORDER[j], one byte each (equity * 255), base85.
MATCHUPS = (
    "(#+7$&Ee1C?cnax+|$hK)6nAX-_GCP)9>KV+{obB+t1$G?AP7S$m-kG?9tc7?cLPi;P27Q)6VL|(9_c3*w*jQ+SSh9;MvsM)5YN8"
    ")78q<(%9D0+0@g|;oj8O<juv@%G2b~%HYV>*3;k9;@8~c#^2uA&e7D()X3n`$IaK+-_+gN&(Gl1)zQ+^(%9AD-p=3F($nGK+t=0E"
    ";^E!l+}z;b($LP#sL!mht-0Q*+s(Gu(XX}Y&9Ud*xUJBr%dFez(XQIL<nGVUv)b0T)7;Otsow9dw93ib(zM6Y)7S3c)3(sy;Lq;r"
    "+0@|G%H#0V)yme-*wfG5*4D@2;Mmdb(#X!s)AG*A;mXm|*5TLR)Ysz1+~VBO)zrw<%iz$(&DYi4)7{?B(cjh8&CSx*($e7H&f(b5"
    "(cI$Q*4WeG;o9BT+Th#K)X|2{qLHexpRcXYx~tT$x3kWzwy?LW+p5v3;JDbW<F&81&(pB!+qmDW%(twrxvsO*&9Tw7$=KuExv}H4"
    "(&(<swYu8ivgF0@xYpFk;?3pM&fL@0&+O~j)VR>g)5g`i(97}4)7I4C*zwcV@59{U+|Jb1%-G7_(Z<W!*WA?G+t1VE)6~$-(ACq-"
    ";@`^N+11hB;oZ>J*WTaY*xKIS+R)I7&ySO<kcq9M&$F(ct+$ZStgE!QuBWHesj0TEw6nRaw$0PBx81a@uF<!wuez<b+Rv`fvC7)8"
    "=DMw_v)sI})VR6lu(Pnpwz}Hd&9Kk1;?wTm;Ly3Z+u^&>%GAl%w$RMG$kgQ2@z%Q3*}KN<?b*@P)6Cb)@6p7}*w^CJ;@r;C@7L7O"
    "$IjT-(cj|E;@Q&C;o#iY*4E(Q+}+vX-`dcQ&xnqPl!&Q{&yuN!udkBLuaK{|vZAM;tdFd)u&B7Mwau%wwyU<St<Situ(z$Yr`fH{"
    "vd`VGwY;yexTv?U+q=87ud=YuxVPcj(5%g|u->?@vDLY|=CQci&(X-<xzo(G%HOWtx#7Rp-n+=UyXw)^*v8+<yVAqX*wpaX@7vDQ"
    "x!Bjw%+l4?(d^&Q@7UAL-{0BP-PqvY-rm{R<J*GMf{%!diiU>Hkcfk+kB!f*imAD+g{Oh1i;JMIh_<e^&Y!ZZiM6M#nzXB}xvjFQ"
    "tgg?l)uFAZyRERZthcVKw6n6Wv$4*%wX)pQtIe^iu(zzT*|oN`t+d?F&&=Yt+s?JjsjjiPthC_dxx})$wb$F?$*|0~(!|f);kVbe"
    "=hW1=*xAj>&ehY>w(`xi+0xJN@ZQwe*5u;d+uPpa*?qN!wZ*x#w|c&{qPD=oeYL~5!MCBZow2OIqPV5Kw#j**!KSCcsJNcNx3<T&"
    "y`rGDe7>TjsHwubtiq_SyrjXxsiV58nzYENrKPKTsH>!`sivT<u&$}Zq@sP9sm7zBu%Dx+r>>{3sHwA?v$CtArLUu?o3Evuq^GE_"
    "s;sf1qp+{3pP!+psi?EBqphW<sIRcArmCc}x38zHs;;PpiG+)ShJw(Kg@KKZhSQ~thm)v<s)4GCkA|m<x2})SgtCo-w4knowyUtS"
    "tFoh>tI@KYj;oEhsH?TGu&AoDv#_qOt<1T$qN1y-(yXnmu&l1Fv$eIav)k9x%eJ_w*t5{BtgN@LwXe3g%Cok#+2gOvtjV_A#?t4p"
    "ve~n<*3`G&;?d03+1b&zxz4xO)zG}U>Co8O?e5&z+27;ZPP2u(wxD{wo3FIL!F#czpS`xRub{BMsI|4b!lkEqp1i`Q!MUQJyRn<7"
    "w78<6pMk-kq`RuEqqn)H!=t6Ctg5%8x}C$Ur=_F3e!#1suC1q|!o#VntE8fVoTsU#oyMf4u&T1E$f&8uny#~~qNS{&uAZ`_o1(3!"
    "u%xiAqo%Q}siB{sq^P2{ucfuFr=+Z~v8tu2v9qqJsj0EAt-!LbvT(k%owm8aZnV9(yt16Kn6an8p0cIBw!w0kwxy)JsI{EEueQRq"
    "y`Gx4bG($KpP<3Ep}wB1yqmzqt){%9m!`s?pqZ$0siK;uq@<XuuAigEpO$x-p~#t^u$Z8xpRA;=qo%Hxsja7<qNJFjovxmgnW&zp"
    "p{u2!ps=N*o|c=Xp`fg-p0A{!nyIX)rKhH<sidc)tE;L^nYguhg`Bpux|)8nzni_Ym#?&}yr`eEp}wM|da=BwwY;FApuVu7sJ6YY"
    "o}YTVo}{0^rJ<s{xTT?|si?fAs-T^zuBfM?qJN~aro*(kp{A{>xU8k1f10SSqN1yztiP(prK_r|shr2dvZbo3pQoh9siCE(sIsZB"
    "tf!~Qsj8=?qNu8(v$LbOsHmo{vaPGBtg@}Gt*NfFsJ641cD|XgvAw)?v7nZ{udl6|uD74HuC~9OpmdhI!KS&goSVC|oT{(8o|v3^"
    "!J3}Aq^6y-y`s3Bo2R6wvYEJ?!lR_7nz(tqrJ|{$rI)|Nq@$*vnR%3?s-&C4nW3ktr>4T9qR5u6t*N7^qMoRjv7eKhrK78&tf!ox"
    "tfHlynVh1eo~g2$tfilytFEW1qoS&_tf;1}uc~CVe{Qw4XmW;uZ@;*4aI$NkZo$2^alLrAzJ8^2!LD?=wV`opw7qL}r=_%ld7P-V"
    "slu|laH+zzsJ_0cxVF8c#=otoq`8E?r>U>6tfa=ltgFDMpn{&P#iOLbo~^5=wyVOXtiq$Nw6Lb7uA;A=w56Y;s->=|x2mS8w4|q^"
    "qo$~;q_eT0v#X`0vaznGr=+m4udA-FuCSMUQL>e?gr9k{oS(U>t*o!9m&Bc~y}F{Tc$>MWySt*FuehtGs;;%4tEPIroxGu>sivp6"
    "q@|*=sH>-=qoSavs=1$<p?jsIv8JV>q^hdErK+TxftshOr>Lo*zNNdVys@gOtDC2%!KJ3HpS_{4te&8<r^BbltE#1`tg4`*s;R4_"
    "#Iv8ss;8y0uC1r3s;{!Fs;I2At$9wivTkopf^dbjbZwn&wP?S&qim;lvBG|@bfmg;q_v`bYqPs*c(S6gf^(myrn$YcpmnmVx2L?k"
    "!K1RGpRT{Grl6vUptq^QxVojPtgpDjrlEnNsKckDte>j7s=uwXsI0D^!oskjsjQ%_qrj$|p{b~~q_eH1p~I-Iqoby(tD?8HrnIT3"
    "rLnQHr>m!~vahPBt+KF;hk=NYiO`LRiIS#&rhTV}hlQ$%kB5!Ug|Uc$wuP&Hv#O_&s<?%LuF$oAgr<wJtf;c2lC7k&uZgL#sGqpA"
    "h>N4D%&n}duBoi5u(GA7v!txi(y6$pt+Caru&lDJv#PVU(XzF$-LSOHt<$cr%+$88wdA(5*W9|Zt=7)f-rv!*w#&8U)zP-Pwb|R&"
    "xV-Ax+Tiipm#wk1mUghanz^o+tE;cIq?WIrx|pqXuehMQxSgAuyse(3tFy3~pLDsJqMW*@o0hn-qM)6rsJES+o0_Mfq@bCddYreN"
    "ytcHPo}j6=sG*m7mZYVkou!(iyraUSsHCN-nZ>}VprNCkrk2H_nVzDftfj52pP$F4rkS0cq@<jzshqH+o}#U+sHLi>uBfJ~r>Lo<"
    "mTX8)fNW8<aBQ+~vu~Y-qi(x*ue*YscdWj1qp+=Zaj?5=d84zmhj*L0r=q#Dpmn0BuCl$osiCr^p|7~RsG+BSsi(NCqNb&)tG=bX"
    "qoIhQr@N-4tfRfDx2(FbuB@t`uB*bPs;Zp2psl2yrm3vNsKc?Psj{c6rlF&$tD?oQqr|MEr?RoJsjR53v#_YEs<N?ba!P=2PH=Z^"
    "uyV9-g>kfSzj$$NfwXzMzInB6qIhp|dT)8TrEh|Ip{upLd~UUQyS#9$czC|CaIl}gezc{fwS}^`uEn>xtG&LpwR)_lf}*W=sHnf7"
    "t-7tgt-q_SzM#X!udAuBp{k?Cr<|jwtG24Lt)-~OtEQo(rKzl>wzi?RtFEWDwXdhErM0!Ns;{rJvQU_HtDm)mrIo0Nsh6CssFt;&"
    "!g{c>y_vO{pRcW{prxp>nwOq=v#Pb9wxyz)vYw@#nWd(poSvSYr>CE|ubh3Lot&wipslE*qMW9qo`9aZsk5S_pPr$jqoJw2ys4R`"
    "rlhB*z@VR*q^F;wth%PAr@^D8r>Ci;p{1s+qpQQDs;sJ{!N;tpsid&8w5hJFuc?`IsF|F&va6`8u9m@;r@OY9qkECIqP4u9nys^_"
    "oTsa|o3osCw3)Y`p{Jgjwwa@tuA`))oSL1OsHV1~pPYK4nzf{vo}Q+txR|D%n|PP1qoSUso4T8`rMjl2rKp&sq`#z}q@22&r=FRh"
    "q@Ts6!m6X8s->r#l%K1joW-x8!K0p`tE;G=r=F~=uc)Y~t*LirytZd&uV|oWzq+$$zHqU<d7Ny#qHMUdoNs5e#b|4vovnIjny9&_"
    "y0o}zr^B+IyuPcowYi+Yzo)33xqQ2#rm&)<oWjAUr@*9`e3hrbpPap#rlq5>sK247$C9kBt)rr*oTZqqoRpcVq_3x~rl6v%sHLBq"
    "pr50kw5*`CsHL8&tE#1;rL3-~siUj1r;CY(jfj7%cBF%deyWF#hK<d8tb>J-iKu_Ds)doQuzrB4(XV`giG#7JrLlvFs)vrTgQ=yY"
    "fsV9@g@UKctFEGsqo<*(vW2L#hn~`yh_kAxv8SV~sI;lHtf;umtFxr3q^r-W)U>M0t+K7Mw6d|>uCuJI+|k$Ku+p%)(zmnO(XzC%"
    "+T+@|xV7Ng>bcpNlvbpVqKuxFnUtfHg}$VDlBk)KuC<_!s->R9rmeWFo_VdUn537bpP;Imz@nC<roEq|ovx{=y0Ms}ccYw|r=p*l"
    "q^O^ws<g3zoS&+jtEQWxqM@msrJ<m#ou{azqPwD?p`od^o}j*=sHLZ>tEQ~FyQQF<q^hB%q@}5>sHm!{!l$gL#>c6wtFN%Gt8iwR"
    "X02wwx|V6BY_Pw1uW6>aZk(>1Y-p~wWo)yZtbJ~vrk%mLu9|GLrm~~9xWJ&VpPHw;r=gsjeV@3bytTHYq@b&~yPctYm!`R(ovE6j"
    "xun9Ur=_T@nY_TQp{1jnsGG;1mz}4huAZx^pQ6X3q@9_dq@tg(u$-`^r=GE_si&u*tF5W0tE;W5PiK#5jBJ=tv}l@htAu;4al4jt"
    "qN%BIZ>+d#cAA=~e{HM4qrbGOp>Uz9t(dsAqob^%o~E~;x38gkrk|dsqoK2^sHdH_qMv`ByR@;Vsi2~!pRA#*xVx#IrmU)^t+}0|"
    "p{S>wr>VTBrKP*4rm(B3qNAdvr>CgEp{lB=p~S+fpscE|wXCVEv9qhAi=l|2m6EKdk+GY=Z>p`ekF}SWtFob)rlYTvjFxq*sj`>2"
    "qnMehm7kZBqo<#kn46TNr<t*@ly{w%lcSlOv7?=vouQtYdz7`MwV9upl$w>Inwz`1sFkCjoujC@mYbcVqnDeexTK+@yrZ3<r=Omh"
    "qobvqrNo-1qn@0?#i*gDqp+&1r>L>6q>r48mXVm1o0VRdnRSh%myd>%o{pxRyrZ0+l$WD<p^%ilnW&+jrm~%&uEVICp`@Iv!l{^)"
    "t)6?Nqo2T}pqr|sy`HSKmwu|bs+^gluAZKqsG+H(q^X;vtD?1_q@taksh^s+qoSq1s;Q>Dt)QKwqNA$6rl+Z*q{F7BrKqT=s;H@{"
    "#Hg#W#IJF)Z%|UOZ-sMjbBLdGyS#O@b+CAHaCT~ZqqcO6cc8kirg(F*cc;2^x_o)6uyU}ZzkI!{qpyavr?aW4r>MEUzo~krq=%rf"
    "d9I|qqPVNLvbVjhvAv|Qt-PnAt)IE4v8bJ<t**bR#ImcVw5YA5rKYQ^rpC0R#H*;JwYjyhsi(5Eu&b`Fv#gAYmX(uikztjbT9Ad8"
    "lWLQijB<;bp^uW5jJ$i3kCmC0oTa#vm!GGRoWhrsrKFFbsF#(ErGTZqk(rjDlAy$xqpFvWfQ*=`wy&$Lx}c(?rKzQxs;k7To0piP"
    "u%n!;pt791q^Y^Y#I~WVq^X~!y`7}1s;s-Hsimi?r>VrHuc@o5vBIpXvUE{YY<Et0b$f`eesqL-Y;~}Icy)Pkd9kr`hI^yFbGCkW"
    "c7d{Yb+CGSy?StUsC|FDs-|{_d$qW_ud%CqeZR1MsHTXiv3;tjdZe|nwz{}^sj+>gw!OiwtFfZDrn;=3rm?BOs>8CZuD+|TrK75>"
    "uBFGZsl~0UsJ64Tsj#fFwy&(QxU{jDm6C6jUzng&kad-mYm%6Zbc2?ji-(kuoL`HMlbD*Jpqh}Co4Aslo|%)RyN#a3mXwgEe4d<?"
    "otUAIo1&eysh5s_j+m{Ll*f{pptqo+skED}lcB+vm6o2Gps%jAv9On*!ke9%nVzYpp_{V0x}&<N!l9_Ro~f&;!=j+Nsi&pErm3p5"
    "Wvgz$acXOPuW-J(Yp!XeZER|BX>hfiYJYB<sIj?oX{v9twrr$ya=5N-vzfMWsGy#(gRiip!MM4fxxA{lbEcetnWl54p1+u=wyD6Z"
    "xTUJTm&L-Xr>CTytD3{4nW3ksvZSu8p`^s9p`o9lq@|;>tDv%~rlPO0tDvi;v9qnIs;{i6oocyit-E=aZ=kqqoU5yBWvjMmZ<VmD"
    "dTpJxouIm_qiva~s;#@YprNgun5nwGpq!t4p`os#qMe_nq_~^5pPGJ_ptqlxr<}B;xTm(PrmCiws;0f8rK6p=oUEOjoTH$?rpBnE"
    "ps1szpPQkjshz^BqQ0r0ps=u}rKhH`uC1r2tF5GMSaE7hgs*jkmUXIXt8;T~b#Ql~ooaq|t-Gqgac!-1qPTOSb9bhxY^tHPc%-_q"
    "vw^apqNu2&u(h?Prgf#Gf}Og0vZ%D9q^P8<rntJjyqmDDr>LpBqoAUwqn)9wx~{0Kzow_Hs;{M^rK_l-sl=(Nuco2D#;d2VrLnTE"
    "t*@`Ou9sY!nRAVmn~`XmxsQjLnxU1Ok&U2sn~ac|nZTl+mzJ2Nl%J-PwxOVno~V<Sk)nE|pR=F0ptHcKnV+bVu7jwWr=FUqmZGGf"
    "!<(#~yQQtAqqwuQpP-_yqoA0apq-|ksHV1_q@19)pr^T^rl+Q-rlGl_r>LW=z@?|IrmCsHtgUcqXM31$y1sF+XsU2&YHx3HoUCYl"
    "Y@EHVqH}7maHF<yuX1;&t!b>Dx^udwp0a$kqOh!^p`p0Cy`XTQoPwUIcA}xRnYX34skFJPr?;A^ufL(AsGqr;tfHEksi?uB!myv8"
    "uBE7*o}Z(lpvASIzpJB|th1`CsHd>4tgNlBtE#h|Y>lUqj;OMkimaTMzn!D4t(kbMq>!AGp`n|omc5ylprpH+nVqDfowuu(nR%R("
    "m71HIlA@uRm7}?)e3zM}o3fvrnV6WMm7|@aq?V+joS?a$oS2`bwUnW{o2I0oq@SOtxw)H~p{1gtp`f6lrJ$anrNE}7q{GIjr>3m0"
    "rdWB6bDolIwV{e>XrhQ|ZLzAOd2XqZpp>qqopGGNpqs3&zNMj{t*NrNwVI-NoS&Jdo}!qjrl6p#v#Wxip0S&<sG*{wou{6sprNUp"
    "sHCN&xSXD!oujjvpS+!=sHvx-rmDHUqM@dwtEHx<qob&$q@|(1s;a2N!mFyRs<o|juV})QXPcp^X=bIeWNVs`r+I6vww$`Lq?>1#"
    "p{SFvu%nx!o|CDuptY``c%7S;qnnwlqoALgv7wiIk-D<8o}iMNo0_PYrn9r9mZ77dp{25$o1CYkk({Hsq@bj|prEFtqnn+fqNSgt"
    "z?rC}ou9zNsiLQ&s<5o7q^hl|f2oUqi-w1Mk*b4{sjq^BsL!x}gM@{TsHL%ojH-Z(w1tPOuz-rPfr5Oh)2g9=kASU$jIx5OvV(-w"
    "f{C-Bp0k{#s;P{ru&0WzmbI;jh>oezqph;1(5$Vhv#hJCpRBj5uB_JDvaZvyvevG!t<<x$wcokjxU{d|<+ZuscuZ7uYj3T6a&B>O"
    "bgrRuhjz2ObA@qqa(1h5b)<K9w{mTCq<40tyRUJAajT}duB*0qd8V*@tfq#ayLz&sc%!AQtGA|gvc7wxwzjUTslB18oVKW+rmelN"
    "r?0}Ns=BYOsG+K?uBWZUps%i|rNhFstF5WGwXd+Rv9Yd`jbf0Jh-!<ForI5!hqrW(g^P}kn4!3jjhCB@oW7QkotlQ3s*RM0op+nG"
    "ikOa>gqy#PnWd44cZ`#&v#h7DvzMZnnx&bOr=`K7mXea3u$-2tp0Aa-nV`15!L*vDo1K-Lx161yqoTH?q?)6qrJ=c`s-~)?t;3|P"
    "s*q}?V6A6oYHDe0m6~LFX|K4dyKZKvZ<w!ZnQUvKrDds^wQ!rXu&aEhoSLDXovN|5rk!r0ntqnJYOb8HnV6oQs-Cg6wzQY1sHLEy"
    "wws`vrJ|ajsj;P^r@o$|r=+5wo}#FtpQy%}q^hBwzrLuYtE8{1s;R56u%~lsY_WE1Z*y*Rt*~%^be_9#w|8xBce8G9w{vs1aBpy%"
    "Y<0P(o@#z^t+ceMt)zBzzo>PmpoN^Oa;2kkpSQBLxUzJnuymfcvcRONq@lE$x2Bq(sj0-MzpJRAx~it2ouH(tpTM-H!mFX4wYRdS"
    "s-&^Av8=4Eu&Iunh^3ReotT}9ikNwwii@+5r<s?av6z^v!lRLxnVF`#qLh!VmU*C=m%f>qkDsEtl%%ngcB8kcn3tohnwXZNnW2}X"
    "pp>Dbp0k>rnVOoUm6ooam!q?#p`Ny<o0grLnWDO%qo$yuz@(p}rJ|&yq@}09sHd#Os%njKX=qGqZ?ds#es!#sr<-qTqjsByY?*U%"
    "zNBiSw6Ai$x}K(ksH38)qMw(rv81AOxUGPlpm(FNtfZi$pr@j-p{25(sj8=<x1yq>qph=_pt+@~rmLx^rK!5RsGy;ytfQ!@q^qf>"
    "sjaQRudJ!Xz^$vPv$U;?NoZ$ZY;Tm2mV9lHm6Vo-lA>ynos^YlotU<mo|2uNm6Vd6fTEzUowT8_zNDC&o|vzAs+pjko2r|eoSwp>"
    "rJ%N`tf{2DwYs69o~)^$ot&nerk$pww4tY?q_m!;yrQ9`s-&c#wxX+~r>DNAsHUc<sKKVGf^~CtbbD;Bc8Phjg>g`Pc5-=dcXFzE"
    "dU1Aja-(~Cv$(K!hI4qVcyM;Ge0{TZcd4n0rM!EyqkX2Yb+3D@d9u8HqJDa{sjRr6u%Uaapr)(2wX3?mr>A$XuBfN3t+1xHzNojW"
    "sHDNiw5zMAwY0adu(YwSi;|a(l8lC#bC-yZk&?cfn3a#1n~a*Ej<lAShMl64jE9+XnwqPYvX`#Jpp}@Skf?g5lc$rDos^cEn8cZ+"
    "n6{>=p`W>_vYVNgucMlkmz$WPm!qGwl%SlRu$Y~=nw+4Yo}HYyoSdYep}eG}qNJ#)z@(#>n}>gph?ZG|i;kF+o4uKelbf88pQ4wP"
    "qneDKqLYw~x?Z4_lAD*ejGmpCnZ=Nde~_4~laiy6n4g!PxWJj1sg0eYnUa>HvY?a2lZ};}xSpS%oRzt(p}4KIl$xWSq@bX@oSnD7"
    "rkuOH!NaS(p`oa+##?G{kC&Z&a*vp~mZ7Aca<reBs)nJRqMW0x#HW>+uAP0Mot(a(pqZwpyq>7Imw>Igrk$IpsGXvlrlX~$prxLo"
    "rlz={pPZwkr=OgxqM@a^qoJU;simK!nX0P1rmUu<roW`ArKh8)r>d!`y{D|P$FE{$uc(`IYN(KykE)=RXO+2{m#V3|l%Sccr>M5G"
    "kCu9umy@QNn3J8LoS3V$t#_E3t&p*#n3|W8pqr+io~xIho};3&nVFWCqOp~lxR|4(q@baqpuM=9n3tiYoS>wdqoJdmq@%s2s-VTb"
    "s;8)^u%~~LkCs$`i<Xj=oST@1l$@K8o12%HwwH~VqnnhFmsYu!l9iH|k)5EEn4pr3VTY5(j+38_o4A&rmz<uJ#EzY!mz0&bjkuAb"
    "mXDX4nVplHpOulpxtN!hkeRr-#G|vIn6|f{#hjO&nV-I$zrn!1y@`mHT8D>>kc^?6m5Y#*wT+gfl#!dXg_*ySjEkLmpOcH1k(Y>^"
    "oRYSri->%Kkf)N0!i$faw3eHtu#u*ToxqoikDryBs-~{0tCpC)k(`&1n5CMSm$b3BowK3BmZG|rq@|<1oT9#=sHec7sHUZ|Z+vv9"
    "m2O#eaBFv^P;8uVbcJtpYOZy5yttlkhHj{%ucoG<b#kJib-1sBqM~)4u6m-SrlGE*d7`O!pRuf|skx=3q@u97p`*Q}tfsB1sj9QH"
    "w5Fh?sjjD}tf{N2q@=2^z^t;bzQnPss;#lIaDaKRS#xM~ZgqZYP;#SocTjP1aI1KDhPs`1hIMbKb#ic^dUdgKeY&oMp`&`Av3R7Z"
    "bf9;peyFN<op*JvskE%9q@#JUo20#?v8k`BsjParwyUJ4sjs53uBNiDtEaH4zNfLOy}z=ot+2DLbZ&``n38XexNVi3kCJGHnUss4"
    "jG&W~l#Qc-rMHxvmz|QJ!<e9!mW_IgnU=DxsH?Q1nxdPhpqi(q!m65=nx3zon5Uqro4cW>vcbH!psSmro1Czno}{Ozv8JS-sHdu_"
    "w4|u1tEs8Gs;8~6b%BU`kgA5WgM_Prg^Y-YsH1+1seyias?Vi_gouW$e2$NXpRj;|&whikf_$%ogsG;Dsj#JkvVM`OhJb>nrK_X0"
    "qn4qJsH%vNiiNJQtfr>Yrl_pdudS@EtE|+suBNcA->|i><FvN4;Dw2jj+?ZSii?<(ik6;~j-HZ)n4XY|indjrlZcp+x{H*TlaIfT"
    "hjxdMp^u20i;|p^n6<=`l%t83pOlG`o3NLT!j6fFmbsXdo0^NWsF$^{v67danx~tXyOx)@yQY@5xVgKdx}>3{sJm2cQ+;)HdvR8H"
    "ZFPH5ad>p9cY08TqjQLJa&UBRccyuGb$WTTvV@_qd8xB{rE+n3e06!GtAC<?d3UL`r=@qLfViQlxvPGyf2^mifU~%zr>v{2sCTfa"
    "e5|abw6wddv#i0uv#zVNx2<VKd2eobXmN3*aCT{Gb8nt;Z?(9paD#7dt!`{^u61^^Z*Qifgq*i_xS)BRtZ%DuuXMAuc$;%}v!$oC"
    "o~)m8rJka%v$UzTz^9~kr>vu#s->o%xVN3Mtf!*CzpkXIqP4cKsHm{8sF`wUn{u^WYOhRfnw@8xtA=lwlc}72pP`w)oTHefrL>)I"
    "wU>aZw|JbHqphB!o~WLvousIrrKY8}pP-<hqotjjv811+wWp<~uce`#qoJUswW6q_qNlv2s;a7_sja1?rM;`Eu*I@*Y-)6>Yh{~m"
    "ak6P|X`XCyptr4Qer~3mv#O}Eb8w}kaiN@qnzeDQo^YX?rkt^#bhf>5ma(>|rKYu;qo1*(n4PM*s->*Brk=8>qMo0grlg;&z@e?H"
    "qMpFRtfi=^w6LqLs;sW8kCkeRmyeEHmy@=SnuM2@kB^F&cb1m1ma&(uyQh<$nv$w_qmY=Gl%J88n47zoqnEm&shp#{vbvg^nyR6g"
    "n3kKDpqQSVvX-Hmo3NUnx0<4)qoJRgv7Dx(o~68|rKO^$slTeGk!q5gcaCUyn3RW?j+=dyj*GWmpqG-CnYECfotu`0l8b(gm5`B+"
    "o{yHEnWDJEmzSuDpq`tPl%TJll*F2hk(aWZnw*%GudJfAud<Vxot~(koWz)(v%sgCwz{~zrnsY@sinbllU-_&VN08EXo-z!Z<Ugh"
    "h=7i>m715KlW&EYqHmIqev*}RwXu_|x1O7yqL!nWm8Zg|nw6cOshyRlovWR<q^G#SyRxCEo}`?mvZJ1)s;jf9q@1XxsHVK8rKhK)"
    "ufe6KtBsVDhL)L=jkl75l%I)?iIPvajEI$xl8l+0kdT^;iBy7+!HbQSi;}sGnUb51ki~<Yppc1=xr?)foREc$kdT~`m6wf=z_pc("
    "ijI=DvBH?JmzJ!wqQR7zla`jfm%zNY!op~6vP^YjZ*6L;O>Lf;u4{g5oT7!Fp_*}Wy_|EknuDsnZkwNYu%VryrK5DFqIaFBr>V80"
    "q@Sgts-B*%qNJv_tE!>1siL8yqNJ*~qo}E+sJp7CrLCx=sHvx`yR5CQ#;$3YWoEjbW~i;IXt%eRqI;m5o1&YamaD0uoMpAGf103f"
    "maL_lnVXxXnXa9htCpmqqoB8$nU<QPwwIi^nxmkjp`f3owYiy^q^6{sqNtswr=XpsrMsl3q`$$hrKPK`sE=!NmzRjPj-Q5+l#QWx"
    "qnMPRmY|TBo}0CclaYRsk&u&-!;qV!vYwo)wU(rfp~0Mzl%SfTv8u7Eubi8}o1L7RpQ@junzOUEq_w8Oo~XE>q^YL9o~F8}rlh^2"
    "rKzb?cWG;NY_CvsUz)CLfN^V{QE6+SadCxgceb5}uDW@mo_DXGa-VaaccGtlpK*1hu%o1(prv=FqOGf?skx`9skC>dqNSmvtG1=7"
    "r>d&Cs-vv2tE;Z4uc^JQt+BwXqLP`Mo2t5^i<73BbeWrzyquVnqMx{#qpp#4r?#S+n4qhdnw6%PqL-belA@!bw4Iiko13AUkglGc"
    "oVcW-p|z)*o1C7Yqr0D?qMV_)qMoCpp{J#%rKrH8rl!EDmXL>-h?<R!k%gOem$ZzNkeiB_zmJxal!JPSj*qgdps25#nU<TQmzJla"
    "zM_<ll$x)Vl%brclC+tiv%0#ooTiwVmz=YmnVO@gv!tMzo}i?pw49`+p`fa@prNQ_Yi6l%YqqzOYI<s)nysUrnQd>RoNlwPft8_e"
    "ov(16o}r(upKYL_ZkVjAq@lQ-o0^uYwUwZ`ov5UyqNAg%wy>a}pQoXpr>LH(rJ|vysJy4Dr@q0frKYm3scDvwWNwz3k(Ymwpt78>"
    "o2rSSo}hA=tAMGOZ=IT)m7=4b!=0X^xSXx1rNFheouHnnsG6Rip`56ntf97=rlO^@ou$2>q^GE)tD>@^sHUZ<x}>P7qo}IFtgD)b"
    "n}U~-ik4NimzA29l$D*9n4N!(k6w+Dg^`h<jgz{OnUbBBlD&qVot2H2wTiWjoRW@}n3$K6oR^iAzqgW)kd~9Pw7;CQp_jI^n!%Wm"
    "nVg=$oV~cczP*ZROq7j|hkk~Zm6(>Gk8gRJw{?<@eT<cJlahszlA^qyo{O}XkCC3fo0ycKn4z$!ucfY<pTLr#nwX-do1&kxv9h4C"
    "slS@0x1yn@q`aM>x2UJ4xTC14r&xSgQCD+{bZ>N6a&mBcc3E|Pgrbb8R(Womf39zKcXM-obai^6czt)Yr+cJ#q<@~8t*3c?uzYr<"
    "t9+lIr>3W^t)zT?q<ples(XK_rmm~1s=TnTx4N)oi;$?Ad7PM(xSf=frJ=c=WwexhtFvd6ke{fUnv|iIpq-tfnxmtkvz?lmn4F)L"
    "l&zkap0c8yrL&=%mYSKMq_mx)qne_-oS&kipQWp(pQgX0r>MfHj);Ssa+;2fmWh~&oS2NYg_DkYi;akhh`x-Iov)IYp0$yqhL*yW"
    "jgOj;nyRC+sH&5hyOx`ii<qLDoR_S!v6{7?x{;-|mZGAfz?`1CqoJX@o}{9wyOe8)Yiy}%YHFWtaIbH6wX1`gpmv|Ia+soNqHUjZ"
    "rKNS9ZELEewx64)p>nX5oVcT;s;Z}@rFFHpqnx9qsG+N?pRlT>psA|3t*5BHzpkvNs<o`4Zh~rYXKQJ2qjPd_Yjd}#f}N;$p{#Y9"
    "Zf<RJadoSza-DT@aj3PTm~x+Uu$rW_rFo}zsiUNHw5g<^q^YN!cC4gxu%eo-uD_+MtGm0ds;sZJs&j^LZfjC+bDec^RB?W}oQ11}"
    "eW9Ows(Ey7b#Z#2sd}Dye08*_ouqf4c%huFr=5GWdZ((eb*ZMNqNl60q<X5Nd%UWrr?0K4tf;T9y05IYzN}q`myn&Ax{hvll#@!4"
    "jeLugbD55Rl$E2GpR|Uan30W{pqP`EpQfRe$diVYm$9IfoSTudtC+U3u92Iio2a3m!I+@8xu~1ExV6Bmy`!O}s=lOzeuIRdfry5J"
    "f2VzV(tL)ofqRL3gr$FsqNs<9v44t*gM)&no}_-QgMfm8qmYJ$iG`o9siB^ph={AKtBI?kiL2GDu!N$jr?9K5wXd+T=9!q9mYI=q"
    "cbJrCj*noBkV%t{e2tg8n4Ok<l$(c#o|~PLm$i?xk)M@}k(`&Al$)8Blfk!_la!U0xUIsUub-H*wVS}1mYtWKz@EFkyurMTW^j;^"
    "X-=GyahQ*Okd$$=s&1>cjGlF#bfKGYsD_rCmYAZcrI(eTsGYf=rnbGlu$+^ho}i<(oS&(urnIZ4rKP8&rnaV|s-vZ<yr!tCW=d$W"
    "QFCKxa+j%xt(bM7oNt+!Zj@4(a;CU(sB?9Pw6>k3maKN5oS31ao~5CvwxD&Rrn8)&xS^w-sid5wu%)P}qold0si>r>u)V9Vnwgho"
    "XSkbdua|tOvu>Q1W2%>#nx&O%nVoNvqoSa<o1mYXoTitXtf8EwwWy(=u%?}wot&YgwW6e^psBN-o~5dxrKzE-q`sr8s=ca~tVwa4"
    "lW&o!eWaLiotSNvqn4qBoN%GGbElk{x3;mKpPsUzo}ZteproUyqOqNxp`fyxrMIG_q^F^&qqL}`siLX8sHdl-tEa=Nt(0bBmv>2$"
    "kAjYrag&p0l9Yv)b+Sm8muHQ4fR~k(proLYhmwqsm$jUgoSc@ilb*4ztCo_SovNFfyq%u1zo?n7yS2TgzNe(5s=8HtXK{C$tbnO("
    "c9x)coNR7uP;7abg?p)TbW*amnW1s8bfTZ2rj~f0bDgoDccP%Ip{cf}rFWpIbEvSXp`xg!xTLMDr>L#FsH~isnQD}$d7+nQm5`W_"
    "mzkWtmzSBjnxUYhyRfsGnwY7hm7ABIm!X@aoUNLmmYA-Xp0Jmpr=gvupRJ#yp`@a?q@tposj9xCrIMIuj){1NjcKc{kfgPkl%1K5"
    "mXD01y`Pqmk(a2NkffKRl(U?mwZOiwo1>MOlbNoZpQ50tu%(@toT8$jxt^e)prfa_p`@s6Z?c(#r?_sKmT|6?Ynp7CZJeZUoo;fY"
    "tfHZso1Jc)maV0nq_?D`p{{P9o1&VfrLm!?r=6s@sGO*$qok*!s;j)Jsjb4Pa+QvMkdkqclS_}Ah_Z2{X||Yci*|;dm6)HFo~n(o"
    "q^+Brzm%VwlA4R3p`5L<xTLG4!knqOou#R$xS*)ErmLm9rlh2-jEQ!Ni-?GZn~ag0kDIc-kdUE@o0*Z2jh3mFi@=PCjghpJjF*>?"
    "tfZQ<t)`8Wmy@HFl)jRgvAm#^w6?aqp}3%)pP;>(g{Vt*XqauLY;JCHZ*pvIahq{+Z?>j#op7IZnU$`madNS7Z>6eqpPrzeqp7Z("
    "ba|h6v!<YRdZMPNrKYO5tf;ZMt%Rv*c5#<=ns9J%RdRH5S9_y$eOb4LcA{^scbKA|pLcbmb#$+we4L!9p{T8>qIi0ze5bCXetnv#"
    "xuv0?tE{lNtf+c>tA2roeT1HWjDd%OgsFUpiiCQ9qky1!ihq84gn)yAhlYN5r=^61fr5ghpRb3Yhk~W2im!`=g@=u;gRQ2lt*u#p"
    "addT)b9HrIb9{AKe4TW8UWZn9pmwHpcAb@YdU%_8c(9p!e08Uxr?8!;fqbHRqOGKRe|f8~r+<H)tgN=7sc)N^bf#`^Y;SIIoTYS{"
    "adK(3r=6N;pL3j<tEHTEv23NKu5zHCpr4_sv!QXNpKiIOqMxRsrmU!~t+}kGti7v_hLwhnw2zvPnT?IbgPWL^iIBI7vxk<8gNKrk"
    "mX4W{j*P#xjfaVfld!A5m93hQu&|cIl9Y~*mA{g-wY<T(taPkRXl`n4b&hg%qEdEfla-6AaF=kNr=Pcua<No~wV!aKqMx0yprD{~"
    "ma1^3q^6XXqq3x_rm3c>w56=BdZ<xvX>n_IZDo9-Q*33Gacik=opO$*qJ?gBu2xg6pmvp#p`xsvrK5IptaYWLsC9Iix1^|<nWm?("
    "s;a4qjh(WVnuoKOiiV%PmyVK^k(a5av8Sk)n7@>pmW-64otTuYtg)Q2ro57%vYDTuq_&lwu%n!uznr0>r&e%qY;SaQZh4?vc4u;G"
    "bDwjSb#JAPR&#QOU0th>d3JQ4psAvfqI!6ze3+h|dw+VXrmA#*nXIs-n5bipW{+~8mu{p?Z*P^Bpr(wRaHFW7u%nc=hqkJpZlIu?"
    "p0J{$p_Zqzm7k%Zs;Z)~pQos+q^P^8uB(@Fnq``iOo(=VnU#;Yj<St`l7^9&mYkTNotBe?u9lXKla;x!z?-q1m8`IxznYhsm!ZIz"
    "y1BQ(w`+!Mu$ys-YD{m9n4y)1r*5*Us+*pLmwlL)oOGU^o2at0p|O&>n~t-gqNt{~pryE~siL=~q^GK&X_&capp})ptFW7!m#3DN"
    "m6Ds3qMV$dub7yXm#~|owwaxtq?)3gv7e%(pQgH`qNSmxtG%SEN|=^zj%a9Uj+dOQhmcT_ij$VJdzE;Vk+E=~v#+O>m!O%Go12G~"
    "ps&5BmAACBy{NmOrKG03l8}gqnv{}`iI%9Eio=VBjFYdHkd>B>t)rH&tf-EZqLrkZn7omiv9+R<vbn6gpu3-&pr^WPagAh2VUm=F"
    "m1m-KucWM$hfkGhbd#HIouQVbtg)Z2a)p|4vz?`ni?o}dwy2|}x1OM-sd1xfY)7%SlbUR-Zkv^sp^t5(YMQZ^YM!2_o1n6vnQok$"
    "Y@(~1nVq7Yu&Jh|sHm&Br>KOKm6nK;u!XRLnvI2skCc^=nUao;!n2c%i;a=7t-qG4nvb!nn825jl9QFblC-zAytr3)SY2Fpo^FhM"
    "a-DHnb$MP`UWa&jc6g4QrIvl5dUm3Bd6lAfe0!ynr+$8Xr>L5PrjeG7j+v&Lm6M#Lm$IIuv9`6Ym5-dAmYcDipPi<ptfHNpo};9p"
    "xt^h>q@Jg`qNS;skB^^^n5BiUsIQiqxsachkeG;=otCY#v74`^yOyD`nVqGkx}2J}rlO#_nxv(ruCJ7ulBH^wn3$iPnVy%Tv72w6"
    "nzEXiw40fjrka<av7e=+q@%l{si>l+q`IP}Q*WMbrE6)Ll5KKumvL;Xlyh-!rJACslc9HWn{Sz>pmKC}rLm%WeVC=Bww|MIoo=OY"
    "kD8a5X=|TuaIcwkkdvyRqpzQyac-b+p{$>Ea-F2JrI(bYrl+!|q>NCGXpWAKm3U=}V|k8{Ppz7ekCBeCr%`~VW|yg|eukNrmYAZs"
    "nX|LDy0vd?RAzQ-Us-BoS65+WdT(K6l7(}3k#=p0R&IKkVs~$bXPRMrUX+f3eV~wNn2wQ~nSYjboRW}CvXqgNmXflqhMK8>l&-6t"
    "znYeumz%wru(7_tws2gUTx)AqZEtCHb9!=dhn%H_cbs%xlX7Q}ns#_$mX4-+cYCUzk$s|xhl`Q2nU0v3kE(*2wyLL%lbe*JoR_<n"
    "oUgf~ma?_4x1P73prNO<oTzkdQj}(8kDGOei<_jXvZ1ALS(tCKouqSdg`S|ZkdCIeqM@XyW?gYzVp?2ge0z3wdYOb}ewln-jd^8$"
    "ns$0(jf0<je1V^ph=HMOZ(Db2Y>|t0a&?)ZsjZ8nc3PHng`1vtdsd#Jt9N~mu%M=pt8i_yNldJiYK)1Lo2-|eo^ouaZlRW)ZEldS"
    "pr(<Mrl+r=sitI<V|kOVZ=J8Jqm-7Nm~efVQI(*thm4o7v#_?Lv!9`<r@4`ImyMTZmzk8QtFD==h`g4Dw3VBmptqZyvZA7*vYe-<"
    "t4vL%h;?jjmYJuVjGA$8q;Zs(m2q`$sG+5Ga+9R7p^~Pyte9$<m6w^Wnwp)Eq^pmenVq4dqqLu-qMxCtx1XV>t(a|_o0plbnwg+&"
    "kE?8;m79~4q^zH&qNJs+vY@D^b#!lVjg+O3b((T(nRIlCmv3@(qK}|>eR!m)lzpRfZ&#zBik6F&b83}Vd!40Pb!4Zkt66e}oS&YM"
    "t+bAdiHVM~r@Wb}n3k=vnY)ybla!RYleM+HxwLqYkB*P7qflw2YLcy>X;gZYn3#Zvny;_1wydP1k&~UAaBP`Tmz$|qZ-B0_vWAVa"
    "pqiqfwwj84c$IN$k5zGro>_8asfVIrePWuKlYFObX?KKoUwdC-d5K+hUvOxKWqe|fi-UoaU38alScGz3c$9Q-Q;B+=d3SlAjevTd"
    "ahq{ejciwfm~e7bmWZKlb#$PajC!G=PG+BFdYztPQ)Z5mjc8YZrmU-ms#jWRX<lQBYFS)+b9;4Oa)ohdV~Lihb&{;9nYxmZk&l<Z"
    "k+ZS4zO#^Mu9ldChqaoUv!kP)v!0=#sA_CvlyO;WfpLOxU2~j;Wn`U|ma(>^maw$0wWPD3nV_P#mzr&GQJ0>oad3;Rp`nbTnrl>J"
    "h<uA|SZ}GLiD9NzS7U5vd{tpzeR5=DhlrK1t**GGu%MWmrMHlik&~Ibm$0m{x3HR=u!@PFubQT(q+*#^bY6{yeRZFnPit9}lZ0`l"
    "Rd-s7eR*_`g|C;GnVYYarmL;9t(lshhp=X2Uxr>?m{FXo"
)


def decode(text):
    """Full 169x169 table: [i][j] is the equity of ORDER[i] against ORDER[j]."""
    data = base64.b85decode(text)
    n = 169
    table = [[0.5] * n for _ in range(n)]
    k = 0
    for i in range(n):
        row = table[i]
        for j in range(i + 1, n):
            e = data[k] / 255.0
            k += 1
            row[j] = e
            table[j][i] = 1.0 - e
    return table


def range_equity(table, weights, i, width):
    """Equity of hand i against the best `width` share of all starting hands (weights: combos per class, ORDER order)."""
    left = width * sum(weights)
    total = eq = 0.0
    for j, w in enumerate(weights):
        w = min(w, left)
        if w <= 0:
            break
        total += w
        eq += w * table[i][j]
        left -= w
    return eq / total if total else 0.5


def _build_pct():
    """PCT[key] = share of all starting hands at least this good; CLS[key] = ORDER index; key = hi * 26 + lo * 2 + suited."""
    pct = [1.0] * (13 * 26)
    cls = [0] * (13 * 26)
    seen = 0
    for k, name in enumerate(ORDER.split()):
        hi, lo = RANKS.index(name[0]), RANKS.index(name[1])
        seen += 6 if hi == lo else 4 if name[2] == "s" else 12
        suited = 1 if name[-1] == "s" else 0
        pct[hi * 26 + lo * 2 + suited] = pct[lo * 26 + hi * 2 + suited] = seen / 1326.0
        cls[hi * 26 + lo * 2 + suited] = cls[lo * 26 + hi * 2 + suited] = k
    return pct, cls


def _build_masks():
    """Per 13-bit rank mask: top rank of a straight (or -1), and its five highest ranks packed."""
    straight, top5 = [-1] * 8192, [0] * 8192
    for mask in range(8192):
        wheel = (mask << 1) | (mask >> 12 & 1)  # ace also plays low
        for top in range(13, 3, -1):
            if (wheel >> (top - 4)) & 31 == 31:
                straight[mask] = top - 1
                break
        packed, n = 0, 0
        for r in range(12, -1, -1):
            if mask >> r & 1 and n < 5:
                packed = packed << 4 | r
                n += 1
        top5[mask] = packed
    return straight, top5


PCT, CLS = _build_pct()
STRAIGHT, TOP5 = _build_masks()
DECK = list(range(52))
TABLE = decode(MATCHUPS)
WEIGHTS = [6 if n[0] == n[1] else 4 if n[2] == "s" else 12 for n in ORDER.split()]


def card(text):
    return RANKS.index(text[0]) * 4 + SUITS.index(text[1])


def hand_pct(c1, c2):
    return PCT[(c1 >> 2) * 26 + (c2 >> 2) * 2 + (1 if (c1 & 3) == (c2 & 3) else 0)]


def hand_cls(c1, c2):
    return CLS[(c1 >> 2) * 26 + (c2 >> 2) * 2 + (1 if (c1 & 3) == (c2 & 3) else 0)]



def score(cards):
    """Strength of the best five of 5-7 cards as one int; higher wins."""
    counts = [0] * 13
    suit_n = [0, 0, 0, 0]
    suit_mask = [0, 0, 0, 0]
    mask = 0
    for c in cards:
        r = c >> 2
        s = c & 3
        counts[r] += 1
        suit_n[s] += 1
        suit_mask[s] |= 1 << r
        mask |= 1 << r
    # Seven cards cannot hold a flush together with quads or a full house.
    for s in (0, 1, 2, 3):
        if suit_n[s] >= 5:
            fm = suit_mask[s]
            sh = STRAIGHT[fm]
            return (8 << 20 | sh) if sh >= 0 else (5 << 20 | TOP5[fm])
    quad = -1
    trips = []
    pairs = []
    singles = []
    for r in range(12, -1, -1):
        n = counts[r]
        if n == 1:
            singles.append(r)
        elif n == 2:
            pairs.append(r)
        elif n == 3:
            trips.append(r)
        elif n == 4:
            quad = r
    if quad >= 0:
        kicker = max(r for r in range(13) if counts[r] and r != quad)
        return 7 << 20 | quad << 4 | kicker
    if trips and (len(trips) > 1 or pairs):
        second = max(trips[1] if len(trips) > 1 else -1, pairs[0] if pairs else -1)
        return 6 << 20 | trips[0] << 4 | second
    sh = STRAIGHT[mask]
    if sh >= 0:
        return 4 << 20 | sh
    if trips:
        return 3 << 20 | trips[0] << 8 | singles[0] << 4 | singles[1]
    if len(pairs) >= 2:
        kicker = singles[0] if singles else -1
        if len(pairs) > 2 and pairs[2] > kicker:
            kicker = pairs[2]
        return 2 << 20 | pairs[0] << 8 | pairs[1] << 4 | kicker
    if pairs:
        return 1 << 20 | pairs[0] << 12 | singles[0] << 8 | singles[1] << 4 | singles[2]
    return TOP5[mask]


# ---- equity network, pasted from equity_net/features.py, equity_net/infer.py and equity_net/weights.txt
N_FEATURES = 72


def net_features(hero, board, widths):
    """13 hero rank counts, 13 board rank counts, the flushiest suit (13 board ranks in it, whether each hero
    card is in it), the other three suits' (hero, board) counts, street one-hot, opponents one-hot, widths sorted,
    then what a small net finds hard to derive: our made-hand class, whether each hole card pairs the board and
    how many board ranks beat it, and the most ranks in one straight window with and without our cards.
    Suits are ordered by their whole content, so renaming suits never changes the output."""
    x = [0.0] * N_FEATURES
    br = [0] * 13
    for c in hero:
        x[c >> 2] += 1.0
    for c in board:
        br[c >> 2] += 1
        x[13 + (c >> 2)] += 1.0
    suits = []
    for s in range(4):
        hm = bm = hn = bn = 0
        for c in hero:
            if c & 3 == s:
                hm |= 1 << (c >> 2)
                hn += 1
        for c in board:
            if c & 3 == s:
                bm |= 1 << (c >> 2)
                bn += 1
        suits.append((hn + bn, bn, hm, bm, hn))
    suits.sort(reverse=True)
    _, bn, hm, bm, hn = suits[0]
    for r in range(13):
        if bm >> r & 1:
            x[26 + r] = 1.0
    hi, lo = max(hero[0] >> 2, hero[1] >> 2), min(hero[0] >> 2, hero[1] >> 2)
    x[39] = 1.0 if hm >> hi & 1 else 0.0
    x[40] = 1.0 if hi != lo and hm >> lo & 1 else 0.0
    for k in range(3):
        x[41 + 2 * k] = float(suits[k + 1][4])
        x[42 + 2 * k] = float(suits[k + 1][1])
    x[47 + (0 if not board else len(board) - 2)] = 1.0
    ws = sorted((1.0 if w >= 0.95 else w for w in widths[:3]), reverse=True)  # bot.py treats 0.95+ as any hand
    x[51 + len(ws) - 1] = 1.0
    for k, w in enumerate(ws):
        x[54 + k] = w
    x[57 + ((score(hero + board) >> 20) if board else 1 if hi == lo else 0)] = 1.0  # score needs 5+ cards
    for k, r in enumerate((hi, lo)):
        x[66 + 2 * k] = 1.0 if br[r] else 0.0
        x[67 + 2 * k] = float(sum(1 for q in range(r + 1, 13) if br[q]))
    for k, cards in enumerate((hero + board, board)):
        m = 0
        for c in cards:
            m |= 1 << (c >> 2)
        m = m << 1 | m >> 12 & 1  # ace also plays low
        x[70 + k] = float(max((m >> t & 31).bit_count() for t in range(10)))
    return x


def net_load(text):
    """[(rows, biases)] per layer, each row its int8 weights times the row's scale; the first layer is stored
    by input column instead, because most inputs are 0 or 1 and a column is then a plain add."""
    data = base64.b85decode(text)
    n = data[0]
    sizes = struct.unpack_from("<%dH" % (n + 1), data, 1)
    k = 1 + 2 * (n + 1)
    layers = []
    for cols, rows in zip(sizes, sizes[1:]):
        q = struct.unpack_from("<%db" % (rows * cols), data, k)
        k += rows * cols
        scales = struct.unpack_from("<%df" % rows, data, k)
        biases = struct.unpack_from("<%df" % rows, data, k + 4 * rows)
        k += 8 * rows
        layers.append(([[v * s for v in q[r * cols:(r + 1) * cols]] for r, s in enumerate(scales)], list(biases)))
    if k != len(data):
        raise ValueError("equity net weights are %d bytes, the header says %d" % (len(data), k))
    layers[0] = ([list(c) for c in zip(*layers[0][0])], layers[0][1])
    return layers


def net_forward(layers, x):
    """[win, tie, lose] for features x: ReLU hidden layers, softmax output."""
    add, mul = operator.add, operator.mul
    cols, h = layers[0]
    for v, col in zip(x, cols):
        if v == 1.0:
            h = list(map(add, h, col))
        elif v:
            h = [a + v * c for a, c in zip(h, col)]
    for rows, biases in layers[1:]:
        x = [v if v > 0.0 else 0.0 for v in h]
        h = [sum(map(mul, row, x)) + b for row, b in zip(rows, biases)]
    m = max(h)
    e = [math.exp(v - m) for v in h]
    s = sum(e)
    return [v / s for v in e]


NET_WEIGHTS = "14sa103ZMZ0Q>j&`t|e<3jFp5{{*bAxUImdm#17|R8B<n|LO_;0RZ#+{r&&@{_p-5{t*KS_vr#4@+d)%?Cn+r&dO$$n_Gcc3P|<p_X6?)<lEQw0T&P;Dl+r$?B)6N0Qmg}0Q~Rr`vd*&_4WA$^#T6^{{jW;0`Ca+Vh`o&{qqOc`un%GLV+_0WnyIY8%6;I7XbbJ^xW$21P~Jt3<M1k1riSf{Ppkj^7aA+{s{mC0|^5I{{sQ}1PclY1_%cR`}+3={PGKd!>AVr>&D{#D!W4Z^!)w-2_7CFARZbQ5eWkH=F15Q3I+-W1_=iQ1Oy5M0Rsg70|NpA1_A^C3=0bZ4FU@QN*xOH;zCJ=f%WnH2JsMDI5lqk0RjpF0P*+z`2Yd|0}>Gx3bg?Q2L}iT0rlwW@bwJ?{QLa?`uhR^`~Cj<0{{R10|f&BCJhMz`~(v62K^HU_kpW0B&qTX7uE&-`v(aI1qT5F0R#a0`t}SB3kM4m4igg*7ZnHy1O^TV1O@^K2?YWR1_TET2nz}g8Oh2__y`gG68Z@c3?qRG(Pe`2_XhpKHUtC$0{`v%`r-Ng0rLzF_y^z%10W0h`TPC>|Ni>_`UeaA0|5T=1_}HA`uz9w=GFQD1oZ|QDi;C>_|m)T1B`+772^Q_4dm|X^7Zip0SX8J0Q?002m}TH_UY^C;^OG?@bdHS_VM-X?DO;T`2PIz_4WMpq7Ve-3**x~6YuB??;-rW-hl%U1``z&6Wi6?;pFV;`0Vci1sw?m`26AU^78ld<K4LE<L2Mz>*nd@>FVV2^Y;1u^z--mE!y1!>EGiE3koUktb_T1`m!Mz7yS|HM&9i6;N$4z^X>cp5kmX{2m%WN2KN8}3l;<d4E+ZV5C{nf2L=8P`TqI@{R;mHwCd*};u0Ul3nLu|fkg-Er5rTw=h+7TAm8WY;O6Y@^7;G!0sZvx_V(=X?CbC8=j7h(?dIt2?ds?0>geg|?(gsJ@bK^N8Sv)z?C0YS3;Xc=3oz(`n!W=Y2nz%5U?n0e5W9hfM2tZjwD|-G1qJ~8`u_U?009aA`uO<y{r&m>`}+I(`~Lp_0RjK~<Oc-)2?g>J2od=O1`)-fDGz_``MnYW{^#Q6=<NOh>Gt#&CLH(q`u_p{`~3Iz`~m>|^!xhz_x|qr`u6<t`1Sz*{r&&<`1u9^58%W!A{yZB3ibk{L}q^=0`mk12L}iV0Ri~?0Q>&||N79<&)Clz92_AV8W|G@1PB5N{{{&I1P2HM3I+xM2nGiL&;|he{s93800Sib?-wET3D1EN^AGv{0vi$x3=9bf2?6@{@bLlz0|EsA0R;#O3K0(n2L}rU2nPlQ1qTKQ0RjRC0SEyF?&ba-|Ni?7016)c*Wp1nrLxQ#_<`pB`VS8d5)1|h_4)Ss1Of>L1O*8U5DyIo3YRDa3<UxP2n7iJ1ONvB{R9F50{#L2)%X7i2?z=L2LBlY1OpWQff(Hf{Qd+A@dEz>{|5&K0|W*J3<|0d6QUFr1poj5|Nj900sH&>`ThX{{{aF31_cZX2LTHL5fKar{QLj{0si;^4*mUs{w1UR0{Q*~{>kYB4fjSfE(Hn-GZp6sA@SK9AqgfH85YJ74+S4KE+7~c6%7yy78M){77`o^YyAxU7!w}++XDLm-gNtPe+(2BB}4__=MD`K5fKRo0Qc|j>FE9a0sR2|{rLg>{{{j3`u6<z`u6(x`TX_x`vC$3{sIF2;syl$_4gX$55*h~0G*-M2^4=8{YVV|0_5J+)7aMb{|^Zd872S!|Na640tO2S3k?wi1pxyE1q1~J1_J~H{Q&+4{s#UB?eg{n6711MBpV9+0{_B)2RfYo1=;ic`XDMD9upSe&g1U^2M!Pr6$=ss2?zA`^7Q`(2@VPa3Iq)b2MP@Z4-F6v4-F3#?jafk1`iSK=K$LS8a?Pv7*c3~3*H9!=>Zi7`0o7X{Nx!VC;L#;L+SP*`4Y+72puU3G#DHg8y5-(4F(Gp3={_e2>}`k#`ydi<`ohAm(D`h&4ENp&pwU+1o-{u0Q&s}2L=5A008#o$+zh3@%Hre^7i}u{`~><_Vx7j_4n`i^zZQW?(z5h_4@Srtm6j!$oD4e^4$gToPqaS<LIBB_0j-5{SOod5(gX)AAum6DDnvd0s{m8{Q&;}`~Cv{0RsH~{{H<2{rms@2?`1Q3jPNI{|W*51pWR52K(~&04!`bAfH|h68;Df0RR2@4ixhzB-_<F#<u_e00RO30|EjA0{{R0{Q&;{|NQ~~{{Q{|1qTKH1^)&84+H`J{|XoO`RxJy{reWj`UQUk|0e+j`uO_y_4M-e`1kqt0uKoV1q1{D|Nr#&^X<#{{{R2{{Q&;|{Qd+8|Md9t_VfGp`1}6>2K(tcAWaAM^$0H&yn(|N3J(JP4GRkk3<?Sa0ssO1`t|?-{{R631O^2L1O*EM0|NvD1OoyD0|f*F1O^5O1_=fS3;+QH2?qxI1p^ZDx=Y{o{Xy25?}7dQ{P^|v`2Yd~2Mi7n4F(7U1p);I0{sI2`vCm?00aX80R#j800R911Ox>J1qB5LAoc<U0tN^4`u*P%0qY6VG=KjK#qR$3`X3(}7XSO_z2fCH^V$a%022!v3={PBfh{Kt5*7{-7Y+>u`wSTf3JL}M1o;B_xX<+$?)U-;6$&vK)bL2}kcZDD`1b|>{rdU%_x1Jl_Vx7j^zsi44h;+r4Gs<s4-XJLJUcx+J3Bo-Jv}`@Q7(p@g`9zest6|c@A?G%`}+$1+`h^R76#b^0}KKB1P>7u5)l*)1^@i@=;rkG_W1ev{R0C82NNRx0sjI10RR310RR2>{Q?9A0tEvE2lo5{5A)tJAp+s<_c29*NI@;<`uF<({0t5U2nPWH1o`ys{tpBP1_}!e4GIYh3j~@100IC41p@^J1p@#I2M7lQ1_TEL7zP9Y@d6v|-~asw5on!(N6#Ht{a^j?0@1<yu`?hW3xOCA8z%n#4G9Si4F&}R3kC-S3Iqun1qucZ3<(Jf3=s(f0tp2N)dvFv4gU8O4-5zl2^xlM^C}r4`7QbN3HtyC1`rqs2M7rZ`~?*J{RImB?+O?L-UbB>1ONv3^Zx<<5(W7L`u__068{SNHVypv^$i&U4(tONH~{Y1^??Ed1n36$2LuHQ3JeGa2le;c+|&mK1_c27`}p?u_4f4t|NQv={rvj-{rvm;2;&0z1NsH|ZVUhX`V12B`T~LU7|`MMIROE(CB5_Z3JVt)78sr}mmaMV;rj&w0sj8_{rCCy{Pg$)1O)~K2LJ{G1^xp7`~3R?`ULs|wG9CK1_J{J3iR^=2T2Vz2r7RP{lOIr0`&L!{`md*{`l|o5Gwoq|N8Uo@A~}z{`U3q0`>X<1_K2F|M&+E2LS>20Q3I(KlAbi(Go=T2m}`7_p<+gF<EmU83+me2lf2{1O*BG0|5jA{P+U`0R8|1{rdFv_WS(*{{R2}{Q>{~{{sR5|Nj0000jU5{{8;>^!fbt{r=Pr6|KFbD(<;~>mMEg0NCpS{WyV$8Z;Tx0SEvB1OEf}`uPL^1pxi|`vd&?`~3Ox{`~a)1_=!U2>=ZP2L=H25B2UD6A$U}{QO8d1I_;f{22rc{SOfk3>FXw2>|%_^4I(P`}zF^0Sycf6Cd3M0|^8I`~n391^xs91OWj21N;L9;|K-={|XT6@%<t24iE7Zfs*?w`WF5J`0w%p!L?40F;0O}KcEi@4g?AZ2Mi4f4GRVX2mb{M0t5#J0s{aA`T+k4{0ROBt}GAs_5%s-{QeaI_X+_(3Dj~a3M~B$_T>Qa0s;#X3?K^o$`$<p1r7)P0sa6D{S*2J{s;C41r7lN_xuYC{RaXC?g{q$_yzj-7XsY^{1*ZP`c&KDD1X)j7C8Y6_!0~a3I721`1JGi`11Jp?f&=(2nYcG0rmI>1PBBJ{{aC60RaaE`S|_^{R8?4;{W^u^a29_^b{KX8Ls}P!hzZs|1t*k4G<6>7ylRz1s$QPIN$*P0s{X4|NZ{@^a~0B0R8^}{saK}{t5g23J?hU3jqlLApQCB68YmB7x?n<_b*z3_AxvJ69EJY{{;{f^#TkI(hM0Fsvimk1Ofv7`Thg}{`vv|0RsO600;p7`vU*~1_uTK1^);DAQc7u2?zuP4+Z`F_XJgc1A7|``4|5I1M~U&_WS+(`~&|12L=fQ3J3%S2>br}0s{s?K|nY_IXFEyJv})(<M9}h6{r@Asp;%4{t6lb_4MoN`5IEdo`2c)2mu562@nty4;2&=2=nR4;q3YJ`}O?${{8#|0tpBP2MP)T2MGlZ00{>H0RsE={`mg{7_F-q+xRG}x0wPUx@NS2uS%@#*<%qN4es*n0sa2YwY(K4Fd_W{1_c8H1pxsE3J(ka0s#U81pWgD1qA~J1Ox>J1qcKN%@7L#2L%HP1qBuS^wSc5@*!;J`ndNC^$iaH`2zp?_xSeo@9^x`RLtDu`1=6?00IF81_}lT3IqiN1q1#91q1r_0RQ>`_Uru$`~wf={^<z;>Ff3*<$=2h{t5j51^@p3{Qmj;{{jaG5g8N`5D^Xy3knPm4-*mz3Jwek3=0bm3k?Yi3J3@W1_lNR(+mM06bAYf4+r}G{QEK`uq=NM1o;8R0u2QT2m}WH{QL9q@Za|N`~La>{saaG0s#jM3Iz%Y2?qrQ2MGfM`~dUu_xSSr?XC9~feAPj@5Cq%*!<+((gUUW`~Cs~3hwab0ty<p84juk!ZrZ}1O)*E{{;U0{`~#{0RI62{R0020sjL10s#U50ssL5`w0pP{`d0+0u1l@3I69`4kdp8|Lz6;1<%yf(&^pW<^Cl{OG^t62nPH8_zeyS77hjU`|<b!1_S&00R#OG1O^8W3KR+p{T&bg<rGoVyp{yz1ms6e!O8!D3|aIB?JFD?6b%Xs5Dy0X^^pAn0{{pO7aAlT7z(Zx5DFF%6bTX(6Au&_2nh=j0S^cf2?qfs0Tm^}+xYOWUbH3v;(xHh>cQ|5<n;6U{PF?y^!)q@6DS7>1O*5R2LuBC`~4II0R;vE0RjU50s;d8{Q(6I2oDDgC-wpb4)4_)8Uyw9;1++;2Ncy%0Z{|)`U?vU3JeJh4+jDE@$U8V_w@7h0SXWl5f2Fi3kCxR1pfd91q1~L2m=NM2M7iS69o$b`vw~A`S1J(7^Cn58-d;V1_Ax~`3)5l85k257z_gHzOe=d1_lWV2L=iV0RavK0s{vG1O)~J1_%ZN1O^5P2n_}c&IASq2MiSJ1pxyE-aZ%1fh}vk{h0Xt_|50;2!R<X?iVW_BM|Qg1q0s)|NaaV4+;VO1^oN}3;qQB0{aR13IYfM0tgHK94rj<5Ci%M59r(tBJjxrQ0Ca(^C1}f|Lyto|NHXY@$>`-9V{dd6bl6U`1SYw_4Dlb{sH{>2KfT{_WJt(00RLE0uBHS*Yyb%0{HdY^#BPE{prV|F@G662<IE}`|I!7`ts55+8j$bKY<Dd2nzxJ{RIO4{{8?82?PBD1`7oS2nYxT1p)yC0RaRDu?G$c2>cBL_vz{L2?y9zbtr6d5o-eP0|o^K1_cEJ0s;X3{rvv{{{jC1{{RC60s#gC0s{jB0|W#D1Oo#F0RR63{saF42L1m1_#F@Uf#nPa`}*V%{^jun{RIC00O{=R>+2#J4H*pp4hbk84iSml@b&Tw0|oy7{QLg)0s;UC{s0C62?Y%Z2?GuUED;R;1P~D3`tITuDjf8$D1nIQ1@8w1^9KY82MGlV3k(GS`tSt?1q=`g2?+)T2L=fg5)=>+5)}{=6A%;^3kU!P00#aA?4=PK2Lby401yNJ2=VbnB7Y<E`t||r`S|+i2@0JkF)!?tFck{}2?+r9{|f&C_yPk23IzxX1_TBS{|gEO1N;RI{t5pBff@t&0}~ha`3nXD4Cvcg4e4z502u`K1_1W?_67419|i*c8VwHg1O*k8Aqxfi2nq`W1po&I_5%q40S5>N1O){H1q25J%MJqg00#{4{Qdp~8td{D5AA;e2nhlF_znsS4hIVh5(feU1@;FD0SE&K3<UuK1qS`u*5TLO+u!Ep=;Y?-91jFQ{5}3bq(Sxf`}_av?&~EL0@tX4Q~Rpt4C(;%1mNM<*5LB?2ooGAHSY=r00jdB3IYQ1=Hc7-1^x8;`}*?k{P+X__x$$y_Wbns?f~=w?)B~D=l6l(N>jif^#d?)K=ld}^%4#I_weoQ`tj@c0}%lN1ONa0`1|nn@$dle_U`fT@AUEY_xJSj^7;D-0|)v5Dg*Tl3;5aM6A;|${s#X%1kHaq^td4a7XbhQ0t5sI0t5pA0S^8B{rvv>{QLg^0S5vC{{jL3000640{{X50|f^J0|5mB3jPEO`3MpX0SyZW`t*S#>*Cap?f47(0RjF01O)&50t6KP5&r=N1O){I1qurZ2NEC&1_uKK1qKHP2?z}Z1_THQ0SXBUwddt5_4*m}?A9U)`WfDZfhO<v{sr~(3+(gy`1Jev`uGtVCM^C02nGEH0}A-|{{$BN1^)gA`vvy=00I631_cKG2>S;BJv}Ya1sM(D205h8Fg_kce;+6+|IP*q@gNBh2NWM34Fn1L>$vmr<=^D#_4gzqCo4_?1_Tia77G;;3=9km5&8uQ0t^or8S5Df2ln{SA{y-Hozhe%LLh&#F4hh95BviX5DW<k2L=ND{Q(Jq`UDFO4hstm2nY!S_5uS01OoyD0t5pB{Qv_900#jE-wX!-1qTf70R90C3is;h6a~8U1pWX3`3npO9~c-51OxNq-t7_;l$B}K3la|!6A}vx5)cy;91RKz4FUoV1_b{B0TBKQtnLaR@BbLW=+hDq;mq|-?Vy4C0Soo~^$!pU0r>t4Iv^1f|Ka}&85Irz0|E2_4G1C|DjpjmAs-hg3?mr^2@MSZ6YCKE5-KG2{{I&00p=7e3Jo#do#25C7{dMe?h6P91qA~E0RH^@_xJz-0s{mD0Ra8{`uF$&0s;dB1p@;D0|Ed5`~3R?`~>_21ONX1)CV9#2lD^?`}Onh02hJ#|Nj3200adC`27J12MY`W_4EV?3km_4{QwCN5)29j1_Jv90|f&H2LcBF{{jUG{{aC9@eBm~{RIjI`uGU}`~mUf27#pZ0P_I^1_c2A0R#X98x9Hr0{;yN0tE*Gfe8i!2Mq@W1P22K2i^$?2L}cP2L}lS2L=cR0}BcX0S5^2{QCe01@-a?8@H(P0{j91_74gS1PJ~A{}>q&2Kg)=3K9++27&zd{R|cf0u2cV3<L-X2LcHH3=j|m3kD1VBKZLd1Ox~R0Q(3K0p{>G1N_?g0rCa`=mZ7^1_=rX1p@*8{`ms}0RjO40RR5~{{H;|009620RaF3009610RjR60s#U63kC!O0{-xU#^MGA00#RC{@O?c0R#j90rB$n0|5*Q1O*5P0sZ>-@A>`$0RsL20}2TK0ssO61O);H1p@{G1Oos30saB|8~p(O>klK==G_Sk3=8&w<fpd<3hM*`2?GKD0RjXB0|NpB1NjOK3kL-U3I_rQ2MGrv9w8+sA|N9q9vm1NtN#sw4S@``2Fv6g_x}O&{QczO>=XD!oA&Px1quK8`}O+=1_Ao{5c>oL2L2Qk3kV7d{r>>~1Nr^^0sQ_3{Qm|90R0B`6af4R{Sp8Z{wn_OCGhGQ1^nyv9zNvvJbyq3`4;~P`_ISC!MzM$EG90Nfj|BG{{#sI69@wW0rB?z{Q3F*0Qms^1pxf?^7Hrx`w998l?E3G4*&KG5dZ)L4E#P#@VU`B^acC|^Z^eJ4F(4S1OWs7`~I*6|11Ln0RjR81O){L1q1~I1_c5H1p)&D0t5sC0t5sE`UC_80|p57{Q(3B1n%=D2!R&#1OEU1{R-pm!xZ=-6)Y7M1}P8(_XqIu5B~HH1PurS|M~9c^YZf${RjC79tsc(2?`Mt790WkB>2<~C<YSx{pR;je;+;l0zUW)>M<k@2?qBB^$`pH3GxLB015&M5Bu@`0s}D)6cHB@5EK>@3J?V#3kVDT3;_xOiTe#92nY@W2J9dm{}Hpg*MZdA0{ZFc8x0Bw2n7ZQ1_}xb5rGE=1_%ZR2?z-Y1^|cy0s#U60s#R70{{c{1p@{G0ssXA69fVW_5lLu_zC&}Dewsu*wG);0MY>l{QCL){r?E|`SS$_1p@~F1qTEN0r~j){rn2``uFnu`1SVm`}X?$`1$`101g5N7q{CQ0{Zp_0QA@F68R6?|9@WI_vQox3KSU*{~7cD5DN(v66rS@92o)}9~BrZD;gdk86FiM7Z48;3l|mz><k|k85bT5f%^wK{SPe<?d=l*Dc9>lAZs$$2FMcX1Ox#A2^I<n2?hW9_x%kS+1<ea4iFI$4Gs?k2m}cT2?qlO0R{gA1O^2C1p@>H2LuEK{|6M_`r`-+`{@lK3xTuy0|@;A{ORfU0SOBR3IqiK2MY%U2?7NG_xS+-0s{d0009E}`~Cp^0{Z?00Q&?B1PB5Q4*&WB{09o_^#ld$4(I_LMo)j`0~ZPQ00{&E1ql57`19e}HYx!C{r~_00095}`T73>{RIE~{{#U4|Nr{_0|o>D1p)*8ARi^#0t^Z41_S^D{R2aR@yPiE`YQnk{SF8U1pop80tEpB1ONg71p@>E00aH|_xS$<2>u2J2Lk{D1Ofs52?zuI2m}ZO7!3pXv?W2M*%}Q71qk(lF%bI_{Sx{N1@QUb)63Z8=>jt#64Va)4)yT#`11n(_UG2`3H|c@1pD&>@%rNO?&RwG=l<;mhtBQu#se{m^cy}BwHL2gw{?FqHXGg<asv4K`3W85=`J+I#)0|#{r&#_{Qm(000IC1{{aF4{{aF50sjC2{{;d6009C12?YQ6{00g5_xAq${RA<e0Psx?{u==Z{RGUAJLHcGJjwVPJjLV{Jo_VDJk!VkJZCc{JZr-`JS7qDJL01DI}7CsJeI)(JX$d{Je3(9JjtGYJPmY8JdRv3JZQPhJ4U*CJS#0HJjQPyJQRweJN<D#JOI8FJX5G%JY}{&JcSZ?JQ)k5JSA(}JG0)>J4t>yJl4YVJ0phuJM8x#Jn^2FJWQMoJVl!;Je%-TJSB?|JVI4(JORG7JNgF}Jgr|dJWS{ZJXB6iJX&m=I~r~3JH;j^JW{9}JYIJ3J1${3JVJqMJZ*gKJN|$GJm*>vJeVVuJlM}`JaCQ$Jj665JnD+hJ9|X8JiikVJZR#FJaW?zJZB?6JY|NfJ0EovJY1{-Jo@I8JX32UJPHOQJbAv^J0CNQJd1A6JBnoMJ4T0HJS#IlJlZjDJg)f!Jk)!zJUsDEJcGnsJa8gGJi)2!J15PSJjh$XJ0bP=J7dg=Jl)WsJfjiQJCLYWJUQ%-JWr*JJS|HeJb=5PJB*HAJOchvy=#J#yu;mFy^swlJ?sf=J;@!tyxHW=y`yP@y@SMoy_QeAytP7(zCtd7J>_E8y~QnVyyv5%y!GrhJ%m>)K9XeEJs|?^z3mBAy#jU`K4F8bJzLJYzF_KEy^^wwJg<9{y+{l6yE79NKC#qBy;^!#ysp@PJ+Yg`J8JoqJnm`uJ!t|jz4Dy&y#6$7J(}n0y$+Beyw31mJzEVxy~-MoJ)f0LJoy8JJl5FkJZ2&cJ>JGvy;$3Wy~LA`JxHHjJ_9_7JPm`4y^-58KAr-HJZtKUy`CUIK0!x<J4E0sJ}^eNJ=4@{y~V`IJwD?lJ$5FoJV@7%J)LQ@J+k~}I<I!PJ2O3rJ%i(;Juo1(J@i8dJ`y;`J(+g3JtjC>JyByBKKl~PJ+2}|JzlywKGqu0JyJ2IJu6<;J5d`Iy+$VvyjF+PJyjjEydK9oKD#KHJ#`5PK7~tGzQ4@JJ=4@my|^Fayv!~LKB7>DJX7`6yc=okJuLPd2n+1_|3d{+3i}l13lQrA4e}Nb84?+;?hyAJAqC-o2KV~@3K{AI3>W|I5gPyy66^IX2n+Du9{C^x74i4(3I`P7@EH~3?hgeH83Hov3lQuL67}R60`~>`2iN%Z@9_xw01gKY76|1A`|SzeA_)2B5*^s5{`<=tBnbe282H^11Q`SK3J?Vo8|DMx75eod`sNJ?4bJZ#5B%r-7V-rN5$o>q;q&+K$LlN%59<j9^%xHABK{Hv7E<{G3j;gc{J`p=8UofNCEgk&RsR*}1uO^yB`$vuM=}T-=@I7uRWL04GAI1K845-z@h|XjEoBiaG%@P&3=9=9?JpGt$JXr%_x0rsSoJ0<2<sCEDdFYi1pVjYBLx@j2?&Gv7x4!>2onMo0`uzy3iA9m0}S`q_Wl0z`Ue0n2mcBO5(ozZ2>=ob2lOfw1q%WB2LAl({}%=12J7|q|0eSE5cT&60siUlISGFa2K4Cq1{m-42?qTq64x9MC>aCy1N`$r^Xl&a|ML|pGa2?4|NQI@_yEfT@BjY{@e?2S2J-+60Rb5V0q+O-1n1)B1rP7~4+`@D1NHnQ?jqFo@cZok{rvg&BKm&{2l(*~0tol^6#m`|`2GS2`Whkw<ogLJ4(k0N5dRzV`}YVI1{Mqe?--%?|Njsa0|_Aw91H#j`VTf8`T5!l4F~Z9{p<?+{0{05_XQph@F*Sn1p);WCGh(I;Rk>64F&)q5b+ZN`~v+F0DlF(BNYr8>d4KV3GUW<2@w}4LLvhH?+(ET?%u8T84D*;;1d<*JpUOW2LmPZB>d&`==mbpEgCQ$FAMz>01`X!-%j@9Hwff32nQeo_xEt%+yEXX1duolBl(yuCLQ)EqV7Bj>KzK7<l+v;6Cx(%`VJts+28df4+;M-5AFV&-{uDBE7b`E=G_hV@h%+Z;pjBw>+Jy|{{{jg=OPRm8OH1{_%JH}8W<`tf$nx2>M9)=&*K{=3;Pz!<meXg7YhRQ?fdD0AqNc-_4?%kE)nZh7$W?!`Tk%J_6hTA8x0>E>=*suBN6!j9`YRiBMc({;13T4A=>{23GC$1?+g0p7ybJ0;q~t41oo`%BJ&CB1q%N54gUrU9?Jmk6c#N0=JXXh00Qs|1oayJ3<d!u0xud9_XE1%4+#z`5)cOuBl`m70|-VT`|<D+69(%76z%!|7x>#J4*w_z^%@-i{`?3bChhzG-4uWL1p@CS_WJ+-016BS4dM+lTPZZq!Uhr~7~|i6Y2q#-GtMhA3l=To7*Q1Y1o8O52lm+kMgJAh7w`Zv2G-P8{Ur1s4`tpUR9E!z3;ZG!@)7Rd1@QG22j}+Uc^PE_BlGnLKlb48>Eq4_JqXwb0RjdW#{dTZ+T#=h4jud-w)GDf;mac~5Dkpz)Ytie+Uoz={K^Lg^49}8z%tYr*B=zh>J{7w%SRCd>I?rF0tglJ03sXwGZPgQ9`(x(<SP6Q4igX`0Gzo2$<i$SITsKA-R=Fq3?Hy61IQmn`6A)$4FJH@4fyr`-xdWs4jR)J78DlY0TKB)3%tz=5(VGLA|e_R79GhM67UHK1qTNG6v)jH0OsuHAlrfY6vFoi3;q(w8wR=Y0g(O;-|8<8+500AAoi0lA^I>GDia|u2C^aB9W3DXGw20>4DBlw8UF(FCnqW8Is_2;3^w&Z_TTjHJ6Y}+`}-Lexe5dH(F6}75dZW7Ox}M3BmV#p1o!vT{t*M;DD(0eA@ZLP+%^ER4!!s*^CAzh`2OS8D$KQk#rzz^q8Pl^^cm<8;<^wk=<?_5<j14L@!8Ai1@VEw^XDis!6MYVl$G$`rk(Moy{+xr!<`$1s1n8D<T#$@nyfmql)(bz^7`@m_!Ju(3I!DL`V#aJ=J)*O_wNG$`wE)Y^!Nn!4E!Ji@Avj1?D`k``U&Rc5dGo&4BP_=?HwEf0{$BM8UPa;^cD#N9}5Wv_alD>5ex7I=phsZ0tNN)>;?7)0|5aB{R0Rr?e7Z!`w#~R=mQAZ?d}d51^Iyh?C%S}>k$3%`s?@*@%H!v><riy>IDMj{So>9>Iw%F^#=<8{RaUF{0#~L0tg5P`T$G`?-B$D0|OBX_x|ew?Fah;`vnaC<sBDF`VR;w8S@ep0u}cs7Z(^5=oEqD;|>D(9sVx@9{lAJ{s&Pv^8~~z0T~bX4&e0={tE6X5C|O#<_sF=1{LliITii*&M0~10SfR4@$e}E777ps1k~FB-T)iI0Q<ouBJ92$(+`os_!^(;2qPZ&$nG(S4eHxB*xAS-y+5iV!5qlT=Dr*Tx3}8I+x5@=FUG=^=PAG97wZoN{oxVk4B#)4<+KXdsKntAIS+v}3G=hSva}NW;Pw0e4fqEL^#}R{`}+X~5DxqS_3{M#3jnzX>-hu&^7{e+^z;1W@%H)p`t<}H_WBX{1@Qp%@gDpL`1=U|_xu9~`uzC`4FCQ5fB!KF{Q3g~@CFb03IO~5?=1W0=?wP>_zDwI_X7Lo`2_y`_Vfzn{`wF$=mUY~`}y+u`3V>H0Q>$8{PY3_{UY=K`Tp$<{T2ED^#2JI00RsK1^W90^#&681_KKU*bYSj01X8M{}UAr7WV4|{NxA;7zrZ#>je)=0Q}<(9Q_aa5Dyd-`Up1+{|(dVC<X^35eOXuEgSg=1^O&D1P13Z3H#py2<rXq5G(N#|NSo<^d9;I?(YUB4fFpN{vCh$3FPe(7WD=N=@Inv80!e+0s|cG1;^*%{|^KTDDMOnFBu6A9ViRp8wh_285isE76|_LB@!6?6aLHK{`xi@3H<9i5m6lzJ{s-q8~^eB4h!iC==bLv-vs9TRO<v9{`)BN8tv)x?FsJo7OMQL_wly@2=Vv5?ZrJJ%iiM*^3B*E@5~4N9{uO#BL%<|Aj^Rk7|a0<4h9Da6bjny@dM`c8v!2n*CNyi7~#1g=z_Y@^9kkV{q(=u3-R#O{oBpW9S6ihpZd@DBJ%|L2J!v)@Wcw>1o-y?^7r`z_Ye002MGGu5c%r^`~>>r2M)*o@(2e42?p@}3-kO41Oxd7_8bNI2>|s42>b8>0{{T}3H9{(1o`*%|NMan1NH;(0R9m73j+WJ3Fi(k^8XO}^XLrP2>j<H66X~h`0e}M1_}Mx4+sJf^alR@3i;y(5DF0q1qA*E4&CAc0vzlTA0q++5FGCX1pxd03H%rN_~q#g2kG+e$OM7<|Kben2<-RW7X$MT6Cwl*2=x^2{QUm)_5}VB5BLcE8T<bE{{{*I5D5<l5DWK#^YH-r8vP0U`vU#$4*L=Q{tE~g1{VPk4G;hQ2?qE4`U3#~`~?9A@A3u%DgF=*`T7R_3I6^1|N8O)5Bc&c{{;i|*aG9p{QCgo+X?^p;rj*J_4Di35AK2Wq!0lF1N;sH@(14u@Cf=L_5ZUQ0}~_I_Wc?o15EP)2Lu{C<@Xfl{|XKTGzSL;LlWEc0}A>Tuk8^D6A{Y-?xN?p0Tzf7{Se?ItJNFulMorSfw9>EDK;DLtK%Y}2h#%O=?mN%FhC3$q0r$A)wU1ez0nAqo%jbpq`}VC@jv80>c;OBBf#*Sz25lQC!Z3h;Vkj8tli$58szjgj3Oi`AK@(d%;_89`r-8+Lje96D)uJV9wP|QCJ28RBqHCX?+xGHH4qW*5B%^1IR{V_>>~|PCQ;lFEMey2{0{Q|_!0vN+6E6C=h^2ZW&=<#^6x6|6ZGNe^ZwBIGV}f+3H15|1M&O5>E!|N3=IYh+4c+Y;nCeH6$k<o_3;Oe=k4q42jB|=;^heb-WB8c=MVVS_Z0mB*c$}}>J<O<6#n}R0}l=nEdmS)M)-jj<`4@P7Xt+h5B~A|;r8aZ-ny^{A?60w4!slZ0{^_J#p><a|H}`(#OoXa2)7K|6!zfT+N;bN>GSsa&HK2`y~ygI&&=4Y0lNyR<L-gtwF?r`_@?ov9_ZEBoU{p-^VN;CtOFh&p5VCv`=KNYJdGU+Ji>HWJA++5JX=mGJo~=aJB|%{J4f65J71LTJAqxuJD`7qJNjWhJj%`yJVOeMJFq6QI`eiDJkR@WJc?|ZJNTTpIy0DxJesvfJPvB`JNEabJ34m?JED4;JQ4MTJlwWWJi15zJMSi|I%lD7J37T8JooDDIu1?czUc7EyX*9Dybt;(zU_A;Jr>B0y`1SzJ%=)ZywBN{Jh;QHy^hXQy(Uxfy|RqHJ8$vJJ+|=pz3#sVJOC?%J+~u?J0+l#y|!gRKE7-bzT}OXyy?3mJ?{7My>wb7JahTpyC!52K1^|dJwQu=y|Sj-J)DDZK9m6(zRV#9><Rnw?;83Ffd>lx^xXOd#pDbO0wDMa;`;{j0bb?Sb1~}GcFf@5I)UyG>>l<MJrDNP5H)P#3Jv7o4<6wG+uRHe;t354e+d!<2_X*;5C0eZ|GDc18}tJ%_1yVmJQwT;JmVW3JU2dvJ@Q6HzCIwIy#"
NET = net_load(NET_WEIGHTS) if NET_WEIGHTS else None


# ---- layer 2: opponent model, pasted from model/profiler.py and model/fitted.py
# Layer 2 opponent model constants, written by model/fit.py from 905 seat-rounds of sim; k=9.
FITTED = {"pop":[[0.0,0.774,0.226],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.457,0.314,0.228],[0.433,0.446,0.121],[0.26,0.395,0.345],[0.472,0.315,0.213],[0.607,0.22,0.173],[0.525,0.225,0.25],[0.333,0.333,0.333],[0.56,0.307,0.133],[0.628,0.163,0.209],[0.333,0.333,0.333],[0.726,0.274,0.0],[0.371,0.517,0.111],[0.0,0.615,0.385],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.306,0.614,0.08],[0.213,0.606,0.181],[0.333,0.333,0.333],[0.446,0.465,0.09],[0.334,0.503,0.163],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.185,0.705,0.111],[0.196,0.677,0.127],[0.0,0.667,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.104,0.84,0.056],[0.177,0.694,0.128],[0.333,0.333,0.333],[0.122,0.817,0.061],[0.232,0.538,0.23],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.064,0.877,0.059],[0.11,0.786,0.104],[0.0,0.685,0.315],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.106,0.858,0.037],[0.166,0.705,0.129],[0.333,0.333,0.333],[0.223,0.719,0.058],[0.327,0.465,0.208],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.036,0.942,0.021],[0.109,0.75,0.141]],"pop_m":[3.3,1.5,1.5,1.5,1.8,1.9,1.3,1.8,2.1,1.5,1.5,1.5,1.5,1.4,1.3,1.7,1.5,1.5,1.5,1.0,3.0,1.5,1.4,1.7,1.5,1.5,1.5,1.5,1.4,1.9,1.0,1.5,1.5,1.5,1.0,4.1,1.5,1.0,2.0,1.5,1.5,1.5,1.5,1.0,1.8,1.1,1.5,1.5,1.5,1.0,3.7,1.5,1.0,1.5,1.5,1.5,1.5,1.5,1.0,2.1],"type_prior":[0.096,0.09,0.084,0.096,0.285,0.083,0.088,0.095,0.083],"types":[[[0.001,0.624,0.375],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.001,0.648,0.351],[0.656,0.217,0.127],[0.105,0.263,0.632],[0.001,0.659,0.34],[0.712,0.031,0.257],[0.421,0.001,0.578],[0.333,0.333,0.333],[0.725,0.192,0.083],[0.682,0.09,0.227],[0.333,0.333,0.333],[0.763,0.236,0.001],[0.183,0.518,0.298],[0.001,0.622,0.377],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.571,0.241,0.187],[0.098,0.241,0.661],[0.333,0.333,0.333],[0.792,0.049,0.16],[0.44,0.008,0.552],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.044,0.549,0.407],[0.06,0.131,0.808],[0.001,0.639,0.36],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.426,0.351,0.223],[0.151,0.389,0.46],[0.333,0.333,0.333],[0.836,0.062,0.102],[0.555,0.04,0.405],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.002,0.456,0.543],[0.027,0.128,0.844],[0.001,0.643,0.356],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.566,0.398,0.035],[0.177,0.619,0.204],[0.333,0.333,0.333],[0.899,0.07,0.031],[0.919,0.043,0.038],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.002,0.72,0.278],[0.072,0.628,0.3]],[[0.001,0.998,0.001],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.333,0.333,0.333],[0.088,0.892,0.021],[0.449,0.402,0.15],[0.333,0.333,0.333],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.333,0.333,0.333],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.333,0.333,0.333],[0.001,0.998,0.001],[0.007,0.986,0.007],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.001,0.998,0.001],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.001,0.998,0.001],[0.002,0.996,0.002],[0.333,0.333,0.333],[0.001,0.998,0.001],[0.016,0.974,0.01],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.001,0.998,0.001],[0.001,0.998,0.001]],[[0.001,0.285,0.714],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.001,0.288,0.711],[0.108,0.473,0.42],[0.32,0.293,0.387],[0.001,0.304,0.695],[0.106,0.24,0.654],[0.449,0.215,0.336],[0.333,0.333,0.333],[0.411,0.081,0.509],[0.523,0.136,0.341],[0.333,0.333,0.333],[0.435,0.564,0.001],[0.431,0.568,0.001],[0.001,0.001,0.998],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.264,0.448,0.287],[0.257,0.557,0.185],[0.333,0.333,0.333],[0.288,0.372,0.34],[0.298,0.369,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.264,0.469,0.267],[0.25,0.559,0.191],[0.001,0.001,0.998],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.165,0.62,0.215],[0.18,0.68,0.14],[0.333,0.333,0.333],[0.151,0.515,0.334],[0.128,0.441,0.431],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.173,0.62,0.207],[0.197,0.584,0.219],[0.001,0.001,0.998],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.141,0.666,0.193],[0.219,0.708,0.073],[0.333,0.333,0.333],[0.154,0.442,0.404],[0.347,0.424,0.229],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.147,0.704,0.149],[0.181,0.644,0.175]],[[0.001,0.873,0.126],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.667,0.214,0.118],[0.571,0.363,0.066],[0.452,0.016,0.532],[0.675,0.214,0.11],[0.729,0.166,0.105],[0.693,0.001,0.306],[0.333,0.333,0.333],[0.738,0.096,0.167],[0.734,0.116,0.15],[0.333,0.333,0.333],[0.998,0.001,0.001],[0.786,0.001,0.213],[0.001,0.595,0.404],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.771,0.228,0.001],[0.071,0.927,0.002],[0.333,0.333,0.333],[0.742,0.257,0.001],[0.282,0.713,0.006],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.679,0.319,0.002],[0.175,0.822,0.003],[0.001,0.47,0.529],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.666,0.001],[0.017,0.98,0.002],[0.333,0.333,0.333],[0.168,0.831,0.001],[0.072,0.916,0.012],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.028,0.97,0.002],[0.001,0.997,0.001],[0.001,0.442,0.557],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.236,0.763,0.001],[0.016,0.978,0.006],[0.333,0.333,0.333],[0.401,0.598,0.001],[0.271,0.705,0.024],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.022,0.977,0.001],[0.006,0.986,0.008]],[[0.001,0.878,0.121],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.802,0.001,0.197],[0.887,0.037,0.076],[0.701,0.157,0.141],[0.857,0.001,0.142],[0.88,0.036,0.084],[0.881,0.025,0.094],[0.333,0.333,0.333],[0.829,0.115,0.056],[0.682,0.09,0.227],[0.333,0.333,0.333],[0.92,0.079,0.001],[0.855,0.1,0.045],[0.001,0.564,0.435],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.767,0.195,0.037],[0.435,0.419,0.147],[0.333,0.333,0.333],[0.86,0.101,0.039],[0.649,0.252,0.099],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.863,0.077,0.06],[0.434,0.387,0.179],[0.001,0.726,0.273],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.439,0.498,0.063],[0.111,0.688,0.2],[0.333,0.333,0.333],[0.618,0.307,0.075],[0.443,0.358,0.199],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.193,0.697,0.11],[0.242,0.628,0.129],[0.001,0.7,0.299],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.717,0.225,0.058],[0.157,0.587,0.256],[0.333,0.333,0.333],[0.836,0.103,0.061],[0.342,0.157,0.501],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.389,0.536,0.075],[0.212,0.55,0.238]],[[0.001,0.497,0.502],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.329,0.332,0.339],[0.333,0.328,0.339],[0.374,0.38,0.246],[0.334,0.337,0.329],[0.333,0.337,0.33],[0.332,0.334,0.333],[0.333,0.333,0.333],[0.326,0.39,0.284],[0.628,0.163,0.209],[0.333,0.333,0.333],[0.499,0.5,0.001],[0.433,0.442,0.125],[0.001,0.499,0.5],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.359,0.359,0.282],[0.385,0.404,0.211],[0.333,0.333,0.333],[0.341,0.333,0.326],[0.326,0.332,0.342],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.436,0.421,0.142],[0.433,0.419,0.148],[0.001,0.493,0.506],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.386,0.35,0.264],[0.411,0.384,0.204],[0.333,0.333,0.333],[0.331,0.346,0.324],[0.374,0.351,0.275],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.431,0.419,0.15],[0.42,0.454,0.126],[0.001,0.501,0.498],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.347,0.408,0.245],[0.382,0.435,0.183],[0.333,0.333,0.333],[0.309,0.389,0.302],[0.411,0.354,0.235],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.437,0.414,0.148],[0.443,0.412,0.145]],[[0.001,0.998,0.001],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.746,0.253,0.001],[0.495,0.504,0.001],[0.563,0.436,0.001],[0.753,0.246,0.001],[0.725,0.274,0.001],[0.744,0.255,0.001],[0.333,0.333,0.333],[0.635,0.325,0.039],[0.628,0.163,0.209],[0.333,0.333,0.333],[0.953,0.046,0.001],[0.876,0.123,0.001],[0.001,0.998,0.001],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.492,0.507,0.001],[0.286,0.71,0.004],[0.333,0.333,0.333],[0.731,0.268,0.001],[0.802,0.196,0.002],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.345,0.653,0.002],[0.519,0.479,0.002],[0.001,0.998,0.001],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.108,0.891,0.001],[0.068,0.921,0.011],[0.333,0.333,0.333],[0.206,0.793,0.001],[0.557,0.403,0.04],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.044,0.955,0.001],[0.358,0.637,0.005],[0.001,0.759,0.24],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.183,0.685,0.132],[0.023,0.68,0.297],[0.333,0.333,0.333],[0.326,0.456,0.218],[0.31,0.144,0.546],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.081,0.827,0.092],[0.107,0.459,0.433]],[[0.001,0.838,0.161],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.718,0.127,0.156],[0.747,0.211,0.043],[0.166,0.631,0.203],[0.723,0.124,0.153],[0.787,0.155,0.057],[0.598,0.29,0.112],[0.333,0.333,0.333],[0.657,0.311,0.032],[0.714,0.181,0.105],[0.333,0.333,0.333],[0.792,0.207,0.001],[0.248,0.665,0.087],[0.001,0.728,0.271],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.649,0.335,0.016],[0.081,0.839,0.08],[0.333,0.333,0.333],[0.643,0.341,0.016],[0.323,0.577,0.1],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.638,0.353,0.009],[0.304,0.619,0.078],[0.001,0.632,0.367],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.182,0.762,0.056],[0.039,0.87,0.091],[0.333,0.333,0.333],[0.11,0.822,0.067],[0.06,0.589,0.351],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.023,0.937,0.04],[0.016,0.843,0.141],[0.001,0.622,0.377],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.233,0.693,0.073],[0.025,0.808,0.166],[0.333,0.333,0.333],[0.303,0.604,0.093],[0.162,0.569,0.269],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.119,0.844,0.036],[0.006,0.705,0.289]],[[0.001,0.658,0.341],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.001,0.654,0.345],[0.268,0.573,0.159],[0.17,0.2,0.63],[0.001,0.658,0.341],[0.634,0.053,0.313],[0.551,0.001,0.448],[0.333,0.333,0.333],[0.812,0.09,0.098],[0.591,0.116,0.292],[0.333,0.333,0.333],[0.773,0.226,0.001],[0.254,0.428,0.318],[0.001,0.483,0.516],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.659,0.232,0.109],[0.147,0.459,0.394],[0.333,0.333,0.333],[0.856,0.009,0.134],[0.823,0.003,0.174],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.001,0.638,0.361],[0.18,0.444,0.376],[0.001,0.133,0.866],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.355,0.351,0.294],[0.054,0.75,0.196],[0.333,0.333,0.333],[0.617,0.033,0.349],[0.347,0.044,0.609],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.001,0.592,0.407],[0.104,0.332,0.564],[0.001,0.185,0.814],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.47,0.429,0.101],[0.091,0.856,0.053],[0.333,0.333,0.333],[0.737,0.153,0.11],[0.313,0.129,0.558],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.333,0.333,0.333],[0.011,0.748,0.242],[0.047,0.538,0.415]]],"type_m":[88.9,20.9,20.9,50.0,21.1,6.5,135.3,50.4,15.0,20.9,20.9,20.9,20.9,32.8,7.9,6.3,20.9,20.9,20.9,10.3,13.6,20.9,44.9,11.5,20.9,20.9,20.9,20.9,14.5,12.2,8.3,20.9,20.9,20.9,6.3,77.0,20.9,20.9,1000.0,20.9,20.9,20.9,20.9,16.2,1000.0,10.1,20.9,20.9,20.9,8.8,47.1,20.9,12.3,1000.0,20.9,20.9,20.9,20.9,25.1,21.9],"ranges":[[[[0.101,0.091,0.096,0.098,0.1,0.109,0.099,0.102,0.102,0.101],[0.0,0.0,0.0,0.0,0.066,0.077,0.145,0.213,0.211,0.288]],[[0.157,0.143,0.146,0.125,0.067,0.035,0.071,0.09,0.086,0.079],[0.0,0.0,0.002,0.05,0.151,0.232,0.143,0.099,0.106,0.218]],[[0.161,0.138,0.134,0.092,0.057,0.072,0.092,0.091,0.072,0.092],[0.001,0.004,0.034,0.122,0.179,0.138,0.099,0.092,0.15,0.181]],[[0.151,0.142,0.106,0.081,0.078,0.091,0.097,0.079,0.067,0.109],[0.004,0.03,0.088,0.141,0.141,0.091,0.082,0.115,0.163,0.144]]],[[[0.11,0.093,0.1,0.099,0.101,0.104,0.095,0.101,0.098,0.101],[0.11,0.093,0.1,0.099,0.101,0.104,0.095,0.101,0.098,0.101]],[[0.107,0.096,0.096,0.096,0.095,0.101,0.094,0.092,0.093,0.129],[0.107,0.096,0.096,0.096,0.095,0.101,0.094,0.092,0.093,0.129]],[[0.108,0.096,0.097,0.099,0.098,0.094,0.094,0.093,0.098,0.123],[0.108,0.096,0.097,0.099,0.098,0.094,0.094,0.093,0.098,0.123]],[[0.103,0.102,0.1,0.1,0.094,0.093,0.095,0.093,0.099,0.121],[0.103,0.102,0.1,0.1,0.094,0.093,0.095,0.093,0.099,0.121]]],[[[0.127,0.11,0.116,0.024,0.026,0.025,0.087,0.166,0.159,0.16],[0.0,0.0,0.0,0.139,0.141,0.141,0.132,0.148,0.146,0.153]],[[0.084,0.058,0.054,0.058,0.083,0.116,0.133,0.144,0.133,0.135],[0.081,0.074,0.077,0.083,0.097,0.117,0.096,0.087,0.104,0.183]],[[0.097,0.058,0.054,0.061,0.088,0.162,0.164,0.146,0.093,0.076],[0.102,0.09,0.085,0.09,0.095,0.101,0.093,0.094,0.106,0.143]],[[0.07,0.049,0.055,0.081,0.146,0.164,0.156,0.103,0.075,0.1],[0.11,0.093,0.092,0.098,0.101,0.095,0.094,0.096,0.098,0.124]]],[[[0.022,0.019,0.021,0.021,0.021,0.056,0.188,0.304,0.287,0.06],[0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.001,0.217,0.782]],[[0.025,0.032,0.056,0.095,0.139,0.171,0.092,0.078,0.116,0.197],[0.0,0.0,0.0,0.0,0.001,0.019,0.062,0.139,0.266,0.512]],[[0.033,0.044,0.083,0.143,0.153,0.108,0.08,0.087,0.12,0.149],[0.0,0.0,0.001,0.003,0.016,0.049,0.103,0.199,0.306,0.322]],[[0.05,0.077,0.145,0.145,0.121,0.077,0.073,0.087,0.092,0.134],[0.001,0.001,0.005,0.023,0.054,0.089,0.169,0.218,0.248,0.192]]],[[[0.063,0.054,0.056,0.061,0.063,0.06,0.06,0.065,0.134,0.385],[0.0,0.0,0.0,0.0,0.0,0.0,0.016,0.037,0.39,0.557]],[[0.094,0.083,0.075,0.086,0.09,0.12,0.105,0.111,0.113,0.124],[0.004,0.003,0.015,0.036,0.08,0.133,0.082,0.062,0.127,0.458]],[[0.074,0.068,0.083,0.109,0.128,0.128,0.118,0.125,0.104,0.061],[0.001,0.0,0.001,0.001,0.002,0.01,0.012,0.041,0.301,0.631]],[[0.08,0.091,0.113,0.122,0.126,0.129,0.109,0.116,0.074,0.04],[0.001,0.001,0.001,0.003,0.011,0.027,0.047,0.119,0.363,0.429]]],[[[0.107,0.094,0.103,0.101,0.099,0.102,0.095,0.098,0.101,0.1],[0.105,0.092,0.096,0.103,0.099,0.103,0.096,0.103,0.099,0.104]],[[0.102,0.094,0.1,0.094,0.1,0.101,0.095,0.093,0.094,0.128],[0.107,0.096,0.097,0.095,0.103,0.098,0.095,0.091,0.091,0.128]],[[0.103,0.101,0.1,0.098,0.1,0.096,0.096,0.096,0.095,0.114],[0.102,0.097,0.099,0.102,0.1,0.092,0.094,0.089,0.1,0.126]],[[0.1,0.099,0.098,0.095,0.104,0.092,0.091,0.094,0.103,0.124],[0.095,0.11,0.107,0.098,0.092,0.089,0.095,0.092,0.099,0.123]]],[[[0.012,0.011,0.011,0.014,0.011,0.012,0.012,0.159,0.34,0.417],[0.012,0.012,0.011,0.014,0.011,0.012,0.013,0.159,0.34,0.417]],[[0.015,0.014,0.023,0.041,0.077,0.099,0.07,0.077,0.131,0.452],[0.015,0.014,0.023,0.041,0.077,0.099,0.07,0.077,0.131,0.452]],[[0.015,0.018,0.033,0.06,0.077,0.069,0.069,0.096,0.226,0.337],[0.016,0.018,0.033,0.06,0.077,0.069,0.07,0.096,0.226,0.336]],[[0.022,0.036,0.055,0.075,0.075,0.088,0.113,0.17,0.275,0.091],[0.0,0.0,0.001,0.001,0.004,0.017,0.025,0.049,0.142,0.761]]],[[[0.016,0.012,0.015,0.015,0.015,0.015,0.015,0.131,0.507,0.259],[0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.169,0.831]],[[0.022,0.022,0.03,0.056,0.107,0.156,0.123,0.119,0.153,0.212],[0.002,0.002,0.002,0.008,0.011,0.02,0.021,0.057,0.134,0.743]],[[0.026,0.032,0.057,0.096,0.142,0.119,0.119,0.142,0.161,0.106],[0.004,0.002,0.005,0.014,0.023,0.028,0.042,0.07,0.287,0.526]],[[0.034,0.058,0.091,0.124,0.135,0.117,0.135,0.156,0.104,0.047],[0.0,0.001,0.001,0.009,0.022,0.053,0.071,0.148,0.311,0.385]]],[[[0.094,0.086,0.088,0.091,0.102,0.106,0.1,0.113,0.107,0.112],[0.0,0.0,0.0,0.0,0.066,0.078,0.148,0.21,0.211,0.287]],[[0.036,0.029,0.029,0.058,0.127,0.196,0.138,0.095,0.109,0.182],[0.0,0.0,0.003,0.045,0.152,0.232,0.144,0.095,0.108,0.221]],[[0.097,0.068,0.083,0.092,0.12,0.114,0.091,0.111,0.113,0.111],[0.0,0.005,0.041,0.107,0.196,0.148,0.081,0.088,0.153,0.182]],[[0.114,0.094,0.088,0.065,0.114,0.118,0.09,0.104,0.086,0.127],[0.003,0.023,0.073,0.154,0.141,0.109,0.066,0.112,0.159,0.16]]]],"share":[0.01254,0.0,0.0,0.05688,0.04992,0.04497,0.19186,0.13157,0.09627,0.0,9e-05,1e-05,0.0,0.02709,0.04907,0.08618,0.0,0.0,0.0,0.03039,0.00629,0.0,0.02612,0.00448,0.0,0.0,0.0,0.0,0.00831,0.00467,0.0599,0.0,0.0,0.0,0.01725,0.00187,0.0,0.00951,0.00042,0.0,0.0,0.0,0.0,0.00589,0.00177,0.04947,0.0,0.0,0.0,0.01229,0.00092,0.0,0.00411,0.00024,0.0,0.0,0.0,0.0,0.00893,0.00072],"bot_type":{"kit/examples/random_bot.py":5,"opponents/shover.py":4,"opponents/nit.py":4,"opponents/starter.py":0,"opponents/maniac.py":2,"opponents/equity_tag.py":4,"kit/examples/tight_aggressive.py":3,"kit/bot.py":0,"opponents/clone_base.py":7,"opponents/trapper.py":6,"kit/examples/calling_station.py":1}}

STREETS = ("preflop", "flop", "turn", "river")
ACTIONS = {"fold": 0, "check": 1, "call": 1, "raise": 2}  # check and call are both the passive "call"
CELLS = 4 * 5 * 3  # street x bet-size bucket x raises this street (0, 1, 2+)
BUCKETS = 10       # hand-strength buckets, 0 weakest
HALF_LIFE = 150.0  # hands for an observation's weight to halve, so a change of style is re-read
RANGE_M = 10.0     # a seat's own showdowns outweigh its type's range after this many
SAMPLES = 40       # random hands a postflop hand is ranked against online
BIG_CALL = 800     # a call this many chips (40% of the 2,000 stack every hand starts with) is a stack-off
TEMPER = 0.05      # weight of each observation in the type posterior, fitted by evaluate.py --fit-temper


def size_bucket(to_call, pot):
    """The bet faced: 0 none, 4 a stack-off call; otherwise as a share of the pot (which holds the bet), 1 under
    0.35, 2 to 0.8, 3 over."""
    if to_call <= 0:
        return 0
    if to_call >= BIG_CALL:
        return 4
    x = to_call / pot
    return 1 if x < 0.35 else 2 if x < 0.8 else 3


def cell(street, size, raises):
    return (street * 5 + size) * 3 + min(raises, 2)


def decisions(history, n):
    """Replay a hand's history (state["history"] format); yields (seat, street index, size bucket, raises
    this street, players in, action index) for each fold, check, call or raise."""
    bets, pot, street, raises, folded = [0] * n, 0, "preflop", 0, 0
    for h in history:
        seat, action, amount = h["seat"], h["action"], h["amount"]
        if h["street"] != street:
            street, bets, raises = h["street"], [0] * n, 0
        if action in ("small_blind", "big_blind"):
            bets[seat] += amount
            pot += amount
            continue
        yield seat, STREETS.index(street), size_bucket(max(bets) - bets[seat], pot), raises, n - folded, ACTIONS[action]
        if action == "raise":
            pot += amount - bets[seat]
            bets[seat] = amount
            raises += 1
        elif action == "call":
            pot += amount
            bets[seat] += amount
        elif action == "fold":
            folded += 1


def showdown_buckets(shown, board, rng, samples):
    """{seat: [bucket per street]} for shown hands: preflop percentile among starting hands, postflop the
    percentile against `samples` random hands on that street's board."""
    hole = {s: [card(c) for c in cs] for s, cs in shown.items()}
    board = [card(c) for c in board]
    out = {s: [min(BUCKETS - 1, int(BUCKETS * (1 - hand_pct(*h))))] for s, h in hole.items()}
    used = set(board) | {c for h in hole.values() for c in h}
    deck = [c for c in range(52) if c not in used]
    for k in (3, 4, 5):
        if len(board) < k:
            break
        b = board[:k]
        ref = sorted(score(rng.sample(deck, 2) + b) for _ in range(samples))
        for s, h in hole.items():
            v = score(h + b)
            pct = (bisect_left(ref, v) + bisect_right(ref, v)) / (2.0 * samples)
            out[s].append(min(BUCKETS - 1, int(BUCKETS * pct)))
    return out


class Profiler:
    def __init__(self, n, fitted, counts=True, types=True, temper=TEMPER):
        """`counts` and `types` off give the weaker versions evaluate.py scores against."""
        self.temper = temper
        f = fitted
        self.pop, self.pop_m, self.types_p, self.type_m = f["pop"], f["pop_m"], f["types"], f["type_m"]
        self.prior = [math.log(w) for w in f["type_prior"]]
        self.ranges = f["ranges"]
        self.log_types = [[[math.log(max(p, 1e-3)) for p in c] for c in t] for t in f["types"]]
        self.use_counts, self.use_types = counts, types
        self.k = len(f["type_prior"])
        self.hand = 0
        self.counts = [[0.0] * (CELLS * 3) for _ in range(n)]
        self.ll = [[0.0] * self.k for _ in range(n)]
        self.shown = [[[[0.0] * BUCKETS for _ in range(2)] for _ in STREETS] for _ in range(n)]
        self.rng = random.Random(0)

    def observe(self, seat, situation, action, hand):
        """One action (0 fold, 1 check or call, 2 raise) by `seat` in `situation` (a cell()) at hand number `hand`."""
        self.hand = hand
        w = 2.0 ** (hand / HALF_LIFE)  # stored weights grow instead of old ones shrinking; the ratio is the decay
        self.counts[seat][situation * 3 + action] += w
        ll = self.ll[seat]
        for t in range(self.k):
            ll[t] += w * self.log_types[t][situation][action]

    def observe_showdown(self, seat, street, action, bucket):
        """`seat` showed a hand in `bucket` after its last action (1 or 2) on `street`."""
        self.shown[seat][street][action - 1][bucket] += 1

    def observe_hand(self, summary, me=None):
        """Feed one finished hand from on_hand_end's summary; `me` is our own seat, left out."""
        hand, last = summary["hand_number"], {}
        for seat, street, size, raises, _, action in decisions(summary["history"], len(self.counts)):
            if seat != me:
                self.observe(seat, cell(street, size, raises), action, hand)
                last[seat, street] = action
        shown = {int(s): c for s, c in summary["shown"].items() if int(s) != me}
        if shown:
            for seat, buckets in showdown_buckets(shown, summary["board"], self.rng, SAMPLES).items():
                for street, b in enumerate(buckets):
                    if last.get((seat, street), 0):
                        self.observe_showdown(seat, street, last[seat, street], b)

    def type_posterior(self, seat):
        decay = self.temper * 2.0 ** (-self.hand / HALF_LIFE)
        lp = [p + decay * l for p, l in zip(self.prior, self.ll[seat])]
        top = max(lp)
        w = [math.exp(x - top) for x in lp]
        z = sum(w)
        return [x / z for x in w]

    def predict(self, seat, situation):
        """(fold, call, raise) probabilities for `seat`'s next action in `situation`."""
        if self.use_types:
            w = self.type_posterior(seat)
            mean = [sum(w[t] * self.types_p[t][situation][a] for t in range(self.k)) for a in (0, 1, 2)]
            m = self.type_m[situation]
        else:
            mean, m = self.pop[situation], self.pop_m[situation]
        if not self.use_counts:
            z = sum(mean)
            return tuple(p / z for p in mean)
        decay = 2.0 ** (-self.hand / HALF_LIFE)
        c = self.counts[seat]
        i = situation * 3
        n = [c[i] * decay, c[i + 1] * decay, c[i + 2] * decay]
        z = sum(n) + m * sum(mean)
        return tuple((n[a] + m * mean[a]) / z for a in (0, 1, 2))

    def predict_types(self, seat, situation):
        """[(weight, (fold, call, raise))]: predict() split by type, each type's rates blended with the seat's
        own counts; their weighted mean is predict()."""
        if not (self.use_types and self.use_counts):
            return [(1.0, self.predict(seat, situation))]
        w = self.type_posterior(seat)
        m = self.type_m[situation]
        decay = 2.0 ** (-self.hand / HALF_LIFE)
        c = self.counts[seat]
        i = situation * 3
        n = (c[i] * decay, c[i + 1] * decay, c[i + 2] * decay)
        out = []
        for t in range(self.k):
            tp = self.types_p[t][situation]
            z = sum(n) + m * sum(tp)
            out.append((w[t], tuple((n[a] + m * tp[a]) / z for a in (0, 1, 2))))
        return out

    def range(self, seat, street, action):
        """Distribution over hand-strength buckets (0 weakest) of `seat`'s hand after `action` (1 or 2) on `street`."""
        w = self.type_posterior(seat)
        own = self.shown[seat][street][action - 1]
        n = sum(own)
        mix = [sum(w[t] * self.ranges[t][street][action - 1][b] for t in range(self.k)) for b in range(BUCKETS)]
        z = n + RANGE_M * sum(mix)  # the fitted ranges are rounded, so sum(mix) is only near 1
        return [(own[b] + RANGE_M * mix[b]) / z for b in range(BUCKETS)]


# ------------------------------------------------------------------ layer 3: skills the picker can play
FOLD, CONT, BET = 0, 1, 2  # the response a read is about: folds, continues (calls or raises), bets or raises


class ValueShove:
    """All in for value into seats that don't fold to a stack-off bet."""
    name = "value_shove"

    @staticmethod
    def applies(bot, state):
        """Preflop, the surest caller's lower-bound call chance; postflop with several players in, the least
        sure one's, since every seat must be a non-folder. That seat is the one the skill is gated and tracked on."""
        c = bot.ctx
        c["shove_seat"] = -1
        if "raise" not in state["legal_actions"] or not c["live"]:
            return 0.0
        if c["pre"]:
            reads = {i: bot._read(i, cell(0, 4, c["raises"] + 1), CONT) for i in c["live"]}
        else:
            reads = {i: bot._read(i, bot._cell_for(state, state["max_raise_to"], i), CONT) for i in c["live"]}
        c["shove_seat"] = (max if c["pre"] else min)(reads, key=lambda i: reads[i][1])
        c["shove_read"] = reads[c["shove_seat"]]
        return c["shove_read"][1]

    @staticmethod
    def move(bot, state, base):
        c = bot.ctx
        if not c["pre"] and base["action"] == "raise" and not c["value"]:  # base's bluff: a non-folder pays it off
            return {"action": "check"} if state["to_call"] == 0 else None
        return {"action": "raise", "amount": state["max_raise_to"]}

    @staticmethod
    def assumptions(bot, state):
        c = bot.ctx
        return [(c["shove_seat"], CONT, c["shove_read"][0])]


class Bluff:
    """Bet a hand base would check into a seat that folds to bets too often; never into a barreller."""
    name = "bluff"

    @staticmethod
    def applies(bot, state):
        c = bot.ctx
        if c["pre"] or state["to_call"] or "raise" not in state["legal_actions"]:
            return 0.0
        if bot._barrel_read(c["j"], c["street"])[1] >= bot.p["barreller_off"]:
            return 0.0
        return bot._read(c["j"], bot._cell_for(state, bot._base_size(state)), FOLD)[1]

    @staticmethod
    def move(bot, state, base):
        return bot._raise(state, bot._base_size(state))

    @staticmethod
    def assumptions(bot, state):
        j = bot.ctx["j"]
        return [(j, FOLD, bot._read(j, bot._cell_for(state, bot._base_size(state)), FOLD)[0])]


class CallShover:
    """Facing a stack-off bet from a seat that shoves far more hands than strength allows, call whenever
    equity against its measured shoving range beats the price, however big the bet."""
    name = "call_shover"

    @staticmethod
    def applies(bot, state):
        c = bot.ctx
        big = state["to_call"] >= 0.3 * bot.stack or max(state["bets"]) >= bot.p["big_bet"] * bot.stack
        if c["j"] < 0 or not big:
            return 0.0
        if c["pre"]:  # equity against the top share of hands it shoves, each later caller holding as much
            m = bot._shove_read(c["j"])[0]
            c["eq_call"] = range_equity(TABLE, WEIGHTS, c["cls"], max(m, 0.02)) ** (1 + c["callers"])
        return bot._shove_read(c["j"])[1]

    @staticmethod
    def move(bot, state, base):
        return bot._call(state) if bot._price(state, {"action": "call"}) > 0 else None

    @staticmethod
    def assumptions(bot, state):
        return []  # its read is the seat's own all-in count, which the next all-in updates


class LetBarrellerBet:
    """Against a seat that bets whenever checked to: check strong and medium hands to it, call or raise its
    bets, never bluff it."""
    name = "barreller"

    @staticmethod
    def applies(bot, state):
        c = bot.ctx
        if c["pre"] or not (c["after"] if state["to_call"] == 0 else c["bettor"] == c["j"]):
            return 0.0
        return bot._barrel_read(c["j"], c["street"])[1]

    @staticmethod
    def move(bot, state, base):
        if state["to_call"] == 0:
            return {"action": "check"} if bot._eq(1.0) > 0.5 or base["action"] == "raise" else None
        if bot._eq(1.0) >= bot.p["big_value"] and "raise" in state["legal_actions"]:
            return bot._raise(state, max(state["bets"]) + 0.75 * (state["pot"] + state["to_call"]))
        return bot._call(state) if bot._price(state, {"action": "call"}) > 0 else None

    @staticmethod
    def assumptions(bot, state):
        c = bot.ctx
        return [(c["j"], BET, bot._barrel_read(c["j"], c["street"])[0])] if state["to_call"] == 0 else []


class ValuePlan:
    """With a hand base bets for value: the same pot fraction every street left, all in by the river."""
    name = "value_plan"

    @staticmethod
    def applies(bot, state):
        c = bot.ctx
        if c["pre"] or state["to_call"] or not c["value"] or "raise" not in state["legal_actions"]:
            return 0.0
        return bot._read(c["j"], bot._cell_for(state, ValuePlan.target(bot, state)), CONT)[1]

    @staticmethod
    def frac(bot, state):
        """f = (((P + 2S) / P) ^ (1 / n) - 1) / 2: betting f of the pot on each of n streets puts stack S in."""
        c = bot.ctx
        pot = max(state["pot"], 1)
        return (((pot + 2.0 * c["stack"]) / pot) ** (1.0 / (4 - c["street"])) - 1.0) / 2.0

    @staticmethod
    def target(bot, state):
        return max(state["bets"]) + ValuePlan.frac(bot, state) * state["pot"]

    @staticmethod
    def move(bot, state, base):
        return bot._raise(state, ValuePlan.target(bot, state))

    @staticmethod
    def assumptions(bot, state):
        j = bot.ctx["j"]
        return [(j, CONT, bot._read(j, bot._cell_for(state, ValuePlan.target(bot, state)), CONT)[0])]


SKILLS = (ValueShove, ValuePlan, Bluff, CallShover, LetBarrellerBet)


class Seat:
    """Per-hand counts the profiler lacks: how wide a seat plays preflop, and direct all-in and
    bet-when-checked-to counts that read a shover or a barreller within a few hands."""

    __slots__ = ("hands", "vpip", "pfr", "shove", "checked", "barrel")

    def __init__(self):
        self.hands = self.vpip = self.pfr = self.shove = self.checked = self.barrel = 0


class Agent:
    def __init__(self, params=None):
        self.p = dict(PARAMS, **(params or {}))
        self.rng = random.Random()
        self.seats = []
        self.me = 0
        self.stack = 2000
        self.bb = 20
        self.spent = 0.0
        self.spots = self.spots_value = 0  # heads-up bluff spots seen, and those where we held a value bet
        self.model = None
        self.ctx = None
        self.on = set()       # (skill, seat) pairs switched on; hysteresis keeps them on down to the off line
        self.track = {}       # (skill, seat) -> [(hand, predicted minus observed response)], newest last
        self.pending = []     # responses a played skill predicted this hand, checked in on_hand_end
        self.hand = 0
        self.stats = {}       # how often each option was played, plus "fallback" and "no_skill"
        gc.disable()  # a collection pause can blow the 10 ms limit

    def on_table_start(self, info):
        n = info["num_players"]
        self.seats = [Seat() for _ in range(n)]
        self.me = info.get("seat", 0)
        self.stack = info["starting_stack"]
        self.bb = info.get("big_blind", 20)
        self.model = (Profiler(n, FITTED, temper=self.p["temper"]) if self.p["profile"]
                      else Profiler(n, FITTED, counts=False, types=False))

    # ------------------------------------------------------------ profiling
    def _rate(self, count, total, prior, k=None):
        k = self.p["prior_hands"] if k is None else k
        return (count + prior * k) / (total + k)

    def _seat(self, i):
        while len(self.seats) <= i:
            self.seats.append(Seat())
        return self.seats[i]

    def _read(self, seat, situation, kind):
        """(mean, lower bound) of the chance `seat` folds, continues or raises in `situation`, over the blend of
        types layer 2 thinks it may be; the bound is the mean less z_conf spreads, so a thin read is low."""
        blend = self.model.predict_types(seat, situation)
        vals = [(w, p[0] if kind == FOLD else 1.0 - p[0] if kind == CONT else p[2]) for w, p in blend]
        m = sum(w * v for w, v in vals)
        sd = math.sqrt(max(0.0, sum(w * (v - m) ** 2 for w, v in vals)))
        return m, m - self.p["z_conf"] * sd

    def _direct(self, count, total, prior):
        """(mean, lower bound) of a per-seat rate under a light prior, so an extreme seat shows in a few hands."""
        k = self.p["light_prior"]
        m = (count + prior * k) / (total + k)
        return m, m - self.p["z_conf"] * math.sqrt(m * (1.0 - m) / (total + k + 1.0))

    def _shove_read(self, i):
        s = self._seat(i)
        return self._direct(s.shove, s.hands, self.p["prior_shove"])

    def _barrel_read(self, i, street):
        s = self._seat(i)
        return max(self._direct(s.barrel, s.checked, self.p["prior_barrel"]),
                   self._read(i, cell(street, 0, 0), BET), key=lambda r: r[1])

    def on_hand_end(self, summary):
        big = self.p["big_bet"] * self.stack
        entered, raised, shoved = set(), set(), set()
        street, bet_open = "preflop", False
        for h in summary["history"]:
            a, i = h["action"], h["seat"]
            if h["street"] != street:
                street, bet_open = h["street"], False
            if a in ("small_blind", "big_blind"):
                continue
            s = self._seat(i)
            if a == "raise" and h["amount"] >= big:
                shoved.add(i)
            if street == "preflop":
                if a in ("call", "raise"):
                    entered.add(i)
                if a == "raise":
                    raised.add(i)
                continue
            if not bet_open:
                s.checked += 1
                s.barrel += a == "raise"
            if a == "raise":
                bet_open = True
        for i in range(len(summary["stacks"])):
            s = self._seat(i)
            s.hands += 1
            s.vpip += i in entered
            s.pfr += i in raised
            s.shove += i in shoved
        if self.model is not None:
            self.model.observe_hand(summary, self.me)
        self._check_predictions(summary)

    def _check_predictions(self, summary):
        """Score each response a played skill predicted against the seat's next action after ours."""
        hist, n = summary["history"], summary["hand_number"]
        for name, seat, kind, pred, start in self.pending:
            a = next((h["action"] for h in hist[start + 1:] if h["seat"] == seat), None)
            if a is None:
                continue
            obs = a == "fold" if kind == FOLD else a != "fold" if kind == CONT else a == "raise"
            t = self.track.setdefault((name, seat), [])
            t.append((n, pred - obs))
            del t[:-self.p["track_n"]]
        self.pending = []

    def _diverged(self, key):
        """A skill's predicted responses stopped happening: their recent misses average past `diverge`."""
        misses = [m for h, m in self.track.get(key, ()) if self.hand - h <= self.p["track_hands"]]
        return len(misses) >= self.p["track_min"] and sum(misses) / len(misses) > self.p["diverge"]

    def _gate(self, name, seat, conf):
        key = (name, seat)
        if self._diverged(key):
            self.on.discard(key)
        elif key in self.on:
            if conf < self.p[name + "_off"]:
                self.on.discard(key)
        elif conf >= self.p[name + "_on"]:
            self.on.add(key)
        return key in self.on

    # --------------------------------------------------------------- acting
    def act(self, state):
        t0 = time.perf_counter()
        try:
            move = self._decide(state, t0)
        except Exception:
            move = self._passive(state)
        self.spent += time.perf_counter() - t0
        return move

    def _decide(self, state, t0):
        self.hand = state["hand_number"]
        base = self._preflop(state) if state["street"] == "preflop" else self._postflop(state, t0)
        return self._pick(state, base) if self.p["picker"] else base

    def _count(self, key):
        self.stats[key] = self.stats.get(key, 0) + 1

    def _pick(self, state, base):
        """Price base and every skill that applies under layer 2's blend; play a skill only when it beats base by
        pick_margin of the pot, choosing among those by a softmax so near-ties mix."""
        c = self.ctx
        p = self.p
        me = state["seat"]
        c["live"] = [i for i, f in enumerate(state["folded"]) if not f and i != me]
        c["raises"] = state["raises_this_street"]
        c["street"] = STREETS.index(state["street"])
        c["multi"] = not c["pre"] and len(c["live"]) > 1  # only the value shove covers a pot of several players
        if c["pre"]:
            c["j"] = c["raiser"]
        elif not c["multi"]:
            j = c["j"] = c["live"][0]
            c["after"] = not any(h["seat"] == j and h["street"] == state["street"] for h in state["history"])
            c["stack"] = min(state["stacks"][me], state["stacks"][j])
        c["eq_call"] = None
        opts = []
        for sk in SKILLS:
            if c["multi"] and sk is not ValueShove:
                continue
            conf = sk.applies(self, state)
            if not self._gate(sk.name, c["shove_seat"] if sk is ValueShove else c["j"], conf):
                continue
            mv = sk.move(self, state, base)
            sized = sk in (ValueShove, ValuePlan) and mv is not None and mv.get("amount") != base.get("amount")
            if mv is not None and (mv["action"] != base["action"] or sized):
                opts.append((sk, mv))
        if not opts:
            self._count("no_skill")
            return base
        pot = max(state["pot"], 1)
        bp = self._price(state, base)
        priced = [(None, base, bp)]
        for sk, mv in opts:
            if sk is ValueShove and c["pre"]:
                raise_by = state["max_raise_to"] - state["bets"][me]
                pr, bar = raise_by * self._value_edge(state), raise_by * p["value_edge"]
            else:
                pr, bar = self._price(state, mv, sk is ValuePlan), bp + p["pick_margin"] * pot
            if pr > bar:
                priced.append((sk, mv, pr))
        best = max(pr for _, _, pr in priced)
        temp = p["pick_temp"] * pot
        w = [math.exp((pr - best) / temp) for _, _, pr in priced]
        x = self.rng.random() * sum(w)
        for (sk, mv, _), wi in zip(priced, w):
            x -= wi
            if x <= 0:
                break
        if sk is None:
            self._count("fallback")
            return base
        self._count(sk.name)
        for seat, kind, pred in sk.assumptions(self, state):
            self.pending.append((sk.name, seat, kind, pred, len(state["history"]) - 1))
        return mv

    # ------------------------------------------------------------- pricing
    def _cell_for(self, state, target, j=None):
        """The situation seat `j` (by default the heads-up opponent) faces after we raise to `target`."""
        j = self.ctx["j"] if j is None else j
        me = state["seat"]
        target = min(target, state["bets"][j] + state["stacks"][j])
        x = target - state["bets"][me]
        return cell(STREETS.index(state["street"]), size_bucket(target - state["bets"][j], state["pot"] + x),
                    state["raises_this_street"] + 1)

    def _base_size(self, state):
        return max(state["bets"]) + self.p["bet_frac"] * state["pot"]

    def _eq(self, share):
        """Heads-up equity against the strongest `share` of the opponent's current range, from one rollout."""
        c = self.ctx
        if "curve" not in c:
            c["curve"] = self._curve(c["hero"], c["board"], c["widths"][0], time.perf_counter())
        curve = c["curve"]
        if not curve:
            return 0.5
        k = max(1, int(round(share * len(curve))))
        return sum(curve[:k]) / k

    def _price(self, state, move, plan=False):
        """Expected chips we end the hand with from the pot, less chips we add from now, if we play `move`."""
        c, p = self.ctx, self.p
        a, pot, owe = move["action"], state["pot"], state["to_call"]
        if a == "fold":
            return 0.0
        if c["pre"]:  # preflop only calls are priced; raises are base's reference point
            if a == "call" or (a in ("raise", "all_in") and owe >= 0.3 * self.stack):
                eq = c["eq_call"] if c["eq_call"] is not None else 0.5
                return eq * (pot + owe) - owe
            return 0.0
        if c["multi"]:
            return self._multi_price(state, move)
        if a == "check":
            eq = self._eq(1.0)
            if not c["after"]:
                return eq * pot
            b = self._barrel_read(c["j"], c["street"])[0]
            bet = p["bet_frac"] * pot  # what it bets, as we would
            return (1.0 - b) * eq * pot + b * max(0.0, eq * (pot + 2.0 * bet) - bet)
        if a == "call":
            return self._eq(1.0) * (pot + owe) - owe
        j, me = c["j"], state["seat"]
        target = state["max_raise_to"] if a == "all_in" else move["amount"]
        if plan:
            return self._plan_price(state, target)
        target = min(target, state["bets"][j] + state["stacks"][j])
        x, y = target - state["bets"][me], target - state["bets"][j]
        blend = self.model.predict_types(j, self._cell_for(state, target))
        return sum(w * (f * pot + (1.0 - f) * (self._eq(1.0 - f) * (pot + x + y) - x)) for w, (f, _, _) in blend)

    def _multi_price(self, state, move):
        """With several players in: each seat continues at layer 2's rate for what it faces, independently, and
        our equity against k of them is the per-seat share of base's multiway equity to the power k."""
        c = self.ctx
        a, pot, owe, bets, me = move["action"], state["pot"], state["to_call"], state["bets"], state["seat"]
        eq = c["eq"]
        if a == "check":
            return eq * pot
        if a == "call":
            return eq * (pot + owe) - owe
        target = state["max_raise_to"] if a == "all_in" else move["amount"]
        x = target - bets[me]
        each = eq ** (1.0 / len(c["live"]))
        dp, put, n = [1.0], 0.0, 0.0  # dp[k]: chance k seats continue; put, n: expected chips they add, and seats
        for i in c["live"]:
            y = min(target, bets[i] + state["stacks"][i]) - bets[i]
            go = 1.0 - self._read(i, self._cell_for(state, target, i), FOLD)[0]
            put, n = put + go * y, n + go
            dp = [(dp[k] if k < len(dp) else 0.0) * (1.0 - go) + (dp[k - 1] * go if k else 0.0) for k in range(len(dp) + 1)]
        y = put / n if n else 0.0
        return dp[0] * pot + sum(dp[k] * (each ** k * (pot + x + k * y) - x) for k in range(1, len(dp)))

    def _plan_price(self, state, first):
        """The geometric plan over the streets left, under each type in the blend: each street the seat continues
        at its rate for that size and its range narrows by it; chips won after this street count at plan_trust."""
        c, p = self.ctx, self.p
        st = c["street"]
        frac = (first - max(state["bets"])) / max(state["pot"], 1)
        pot, inv, steps = float(state["pot"]), 0.0, []
        for k in range(4 - st):  # the sizes are fixed by the plan, so each street's situation is too
            bet = max(0.0, min(frac * pot, c["stack"] - inv))
            sit = cell(st + k, size_bucket(bet, pot + bet), (state["raises_this_street"] if k == 0 else 0) + 1)
            steps.append((pot, inv, self.model.predict_types(c["j"], sit)))
            pot += 2.0 * bet
            inv += bet
        total = 0.0
        for t, (wt, _) in enumerate(steps[0][2]):
            reach, ev, trust = 1.0, 0.0, 1.0
            for pk, ik, blend in steps:
                f = blend[t][1][0]
                ev += trust * reach * f * (pk - ik)
                reach *= 1.0 - f
                trust *= p["plan_trust"]
            ev += trust / p["plan_trust"] * reach * (self._eq(reach) * pot - inv)
            total += wt * ev
        return total

    # ------------------------------------------------------------------ base
    @staticmethod
    def _passive(state):
        return {"action": "check" if "check" in state["legal_actions"] else "fold"}

    @staticmethod
    def _call(state):
        return {"action": "call" if "call" in state["legal_actions"] else "check"}

    def _raise(self, state, target):
        if "raise" not in state["legal_actions"]:
            return self._call(state)
        lo, hi = state["min_raise_to"], state["max_raise_to"]
        target = int(target)
        if target >= 0.6 * hi:
            target = hi  # past this point a fold later is never right, so commit now
        elif target > lo:
            j = self.p["size_jitter"]  # stops other bots fingerprinting us by a sizing formula
            target = int(target * (1.0 + self.rng.uniform(-j, j)))
        return {"action": "raise", "amount": max(lo, min(target, hi))}

    def _over(self, x, line):
        """x >= line, except within mix_band of the line, where the chance slides linearly from 0 to 1."""
        band = self.p["mix_band"]
        d = x - line
        return d >= band or (d > -band and self.rng.random() < (d + band) / (2.0 * band))

    def _preflop(self, state):
        p = self.p
        me, n, bb = state["seat"], len(state["stacks"]), state["big_blind"]
        c1, c2 = (card(c) for c in state["hole_cards"])
        pct = hand_pct(c1, c2)
        bets, to_call = state["bets"], state["to_call"]
        top_bet = max(bets)

        raises, limpers, raiser, callers_of_raise = 0, 0, -1, 0
        raised, entered = set(), set()
        for h in state["history"]:
            if h["action"] == "raise":
                raises += 1
                raiser = h["seat"]
                callers_of_raise = 0
                raised.add(h["seat"])
            elif h["action"] == "call":
                entered.add(h["seat"])
                if raises:
                    callers_of_raise += 1
                else:
                    limpers += 1

        cls = hand_cls(c1, c2)
        self.ctx = {"pre": True, "cls": cls, "raised": raised, "entered": entered, "raiser": raiser,
                    "callers": callers_of_raise, "value": False, "bettor": raiser}
        committed = raises and (top_bet >= p["big_bet"] * self.stack or to_call >= 0.3 * self.stack)
        if committed:
            # Equity against the raiser's estimated range (and each caller holding the same) against the pot odds.
            eq = range_equity(TABLE, WEIGHTS, cls, self._raise_width(raiser, raises, top_bet)) ** (1 + callers_of_raise)
            if self._over(eq, to_call / (state["pot"] + to_call) + p["allin_margin"] - p["risk"]):
                return {"action": "all_in"}
            return self._passive(state)

        if raises == 0:
            behind = (state["button"] - me) % n
            behind = 1 if behind == n - 1 else 0 if behind == n - 2 else behind + 2
            limit = p["iso_raise"] if behind == 0 else p["open"].get(behind, 0.12)
            if self._over(limit, pct):
                return self._raise(state, (p["open_bb"] + limpers) * bb)
            return self._passive(state)

        width = self._raise_width(raiser, raises, top_bet)
        depth = pct / width  # 0 = top of the raiser's range, 1 = its bottom
        crowd = 0.7 ** callers_of_raise  # callers behind a raise hold real hands too
        if self._over(p["threebet_r"] * crowd, depth):
            return self._raise(state, top_bet * 3 + to_call * callers_of_raise)
        cheap = to_call <= p["setmine_cost"] * self.stack
        if cheap and (c1 >> 2) == (c2 >> 2):
            return self._call(state)
        if to_call <= 0.08 * self.stack and self._over(min(p["call_r"] * width, p["call_cap"]), pct):
            return self._call(state)
        return self._passive(state)

    def _raise_width(self, raiser, raises, top_bet):
        """Share of hands the last preflop raiser holds, from how often it raises and shoves."""
        p = self.p
        opp = self._seat(raiser)
        pfr = self._rate(opp.pfr, opp.hands, p["prior_pfr"])
        shove = self._rate(opp.shove, opp.hands, p["prior_shove"])
        if top_bet >= p["big_bet"] * self.stack:
            width = shove
        elif raises >= 2:
            width = max(pfr * 0.3, shove)
        else:
            width = pfr
        return max(width, 0.02)

    def _value_edge(self, state):
        """Expected gain of raising to the max, per chip raised, if it is called: each live seat calls a stack-off
        at layer 2's rate with that top share of what it holds; multiway equity is the product of heads-up ones."""
        p, c = self.p, self.ctx
        dp, q = [1.0], [1.0]  # by number of callers: sum of P(callers) * equity, and P(callers)
        for i in c["live"]:
            s = self._seat(i)
            call = self._read(i, cell(0, 4, c["raises"] + 1), CONT)[0]
            if i in c["raised"]:
                held = self._rate(s.pfr, s.hands, p["prior_pfr"])
            elif i in c["entered"]:
                held = self._rate(s.vpip, s.hands, p["prior_vpip"])
            else:
                held = 1.0
            e = range_equity(TABLE, WEIGHTS, c["cls"], max(0.02, call * held))
            ndp, nq = [0.0] * (len(dp) + 1), [0.0] * (len(q) + 1)
            for k in range(len(dp)):
                ndp[k] += dp[k] * (1.0 - call)
                ndp[k + 1] += dp[k] * call * e
                nq[k] += q[k] * (1.0 - call)
                nq[k + 1] += q[k] * call
            dp, q = ndp, nq
        return sum(dp[k] * (k + 1) for k in range(1, len(dp))) - (1.0 - q[0])

    def _postflop(self, state, t0):
        p = self.p
        me = state["seat"]
        hero = [card(c) for c in state["hole_cards"]]
        board = [card(c) for c in state["board"]]
        pot, to_call = state["pot"], state["to_call"]
        folded, bets = state["folded"], state["bets"]
        live = [i for i in range(len(folded)) if not folded[i] and i != me]

        raised_pre = set()
        bettor = -1
        for h in state["history"]:
            if h["action"] == "raise":
                if h["street"] == "preflop":
                    raised_pre.add(h["seat"])
                elif h["street"] == state["street"] and h["seat"] != me:
                    bettor = h["seat"]

        widths = []
        for i in live[:3]:
            s = self._seat(i)
            if i in raised_pre:
                widths.append(max(self._rate(s.pfr, s.hands, p["prior_pfr"]), 0.08))
            else:
                widths.append(max(self._rate(s.vpip, s.hands, p["prior_vpip"]), 0.15))
        eq = self._equity(hero, board, widths, t0)
        self.ctx = {"pre": False, "hero": hero, "board": board, "widths": widths, "bettor": bettor, "value": False,
                    "eq": eq}

        if to_call == 0:
            frac = p["bet_frac"]  # one size for value and bluffs alike
            spot = len(live) == 1 and me in raised_pre
            self.spots += spot
            if self._over(eq, p["value"]):
                self.spots_value += spot
                self.ctx["value"] = True
                return self._raise(state, max(bets) + frac * pot)
            if spot:
                # Break-even mix: bluffs / bets = B / (P + 2B), given how often our bets here are value.
                f = frac / (1.0 + 2.0 * frac)
                v = min(self._rate(self.spots_value, self.spots, p["prior_value_share"]), 0.95)
                if self.rng.random() < f * v / ((1.0 - f) * (1.0 - v)):
                    return self._raise(state, max(bets) + frac * pot)
            return self._passive(state)

        odds = to_call / (pot + to_call)
        street = STREETS.index(state["street"])
        aggr = self.model.predict(bettor, cell(street, 0, 0))[2] if bettor >= 0 else p["prior_aggr"]
        size = min(1.0, to_call / max(pot - to_call, 1))
        need = odds + p["call_margin"] + p["passive_margin"] * (1.0 - aggr) * size
        if self._over(eq, p["big_value"] + 0.5 * p["passive_margin"] * (1.0 - aggr)):
            self.ctx["value"] = True
            return self._raise(state, max(bets) + 0.75 * (pot + to_call))
        if self._over(eq, need - p["risk"]):
            return self._call(state)
        return self._passive(state)

    def _equity(self, hero, board, widths, t0):
        """Chance of winning at showdown against one hand per width, each drawn from that top share."""
        p = self.p
        if p["equity_net"] and NET:
            win, tie, _ = net_forward(NET, net_features(hero, board, widths))
            return win + 0.5 * tie
        trials = p["trials"] if self.spent < p["round_budget_s"] else p["trials"] // 4
        deadline = t0 + p["decision_ms"] / 1000.0
        used = set(hero)
        used.update(board)
        deck = [c for c in DECK if c not in used]
        missing = 5 - len(board)
        need = missing + 2 * len(widths)
        sample, clock = self.rng.sample, time.perf_counter
        fixed = score(hero + board) if not missing else 0
        won = 0.0
        done = 0
        for t in range(trials):
            if not t & 7 and clock() > deadline:
                break
            draw = sample(deck, need)
            ok = True
            k = missing
            for w in widths:
                if w < 0.95 and hand_pct(draw[k], draw[k + 1]) > w:
                    ok = False
                    break
                k += 2
            if not ok:
                # Outside a seat's range: keep one deal in four so the estimate never starves.
                if t & 3:
                    continue
            full = board + draw[:missing] if missing else board
            mine = score(hero + full) if missing else fixed
            best = 0
            k = missing
            for _ in widths:
                v = score(draw[k:k + 2] + full)
                if v > best:
                    best = v
                k += 2
            won += 1.0 if mine > best else 0.5 if mine == best else 0.0
            done += 1
        return won / done if done else 0.5

    def _curve(self, hero, board, width, t0):
        """Heads-up showdown results against hands from the top `width` share, strongest on the current board
        first, so the mean of the first c share is our equity against the part of its range that continues."""
        p = self.p
        trials = p["trials"] if self.spent < p["round_budget_s"] else p["trials"] // 4
        deadline = t0 + p["decision_ms"] / 1000.0
        used = set(hero)
        used.update(board)
        deck = [c for c in DECK if c not in used]
        missing = 5 - len(board)
        sample, clock = self.rng.sample, time.perf_counter
        out = []
        for t in range(trials):
            if not t & 7 and clock() > deadline:
                break
            for _ in range(12):  # a hand from its range, giving up after a few misses so a thin range never starves
                draw = sample(deck, missing + 2)
                if width >= 0.95 or hand_pct(draw[missing], draw[missing + 1]) <= width:
                    break
            opp = draw[missing:]
            full = board + draw[:missing]
            mine, theirs = score(hero + full), score(opp + full)
            out.append((score(opp + board), 1.0 if mine > theirs else 0.5 if mine == theirs else 0.0))
        out.sort(reverse=True)
        return [w for _, w in out]
