"""Tight-aggressive Hold'em bot that profiles each seat and shifts its thresholds to exploit it.

One file, standard library only: the tournament sandbox loads nothing else.
"""
import base64
import gc
import random
import time

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
    "bet_frac": 0.66,
    "big_bet_frac": 0.90,
    "call_margin": 0.06,       # equity needed beyond pot odds against a constant bettor
    "passive_margin": 0.16,    # extra equity needed against a seat that rarely bets
    "bluff_fold_rate": 0.55,   # bluff heads-up only when the seat folds to bets this often
    "bluff_freq": 0.60,
    "risk": 0.0,               # added to every stack-off threshold; raise it to chase variance
    "prior_hands": 12.0,       # how many hands of "average player" each seat's stats start with
    "prior_vpip": 0.30,
    "prior_pfr": 0.15,
    "prior_shove": 0.03,
    "prior_aggr": 0.30,
    "prior_fold": 0.45,
    # Exploiting seats that do not fold: these rates use a light prior so a station shows within ~15 hands.
    "sticky_prior": 3.0,       # hands of prior behind the call-big-bet and fold-to-bet rates below
    "prior_pfcall": 0.30,      # share of big preflop raises a seat continues against
    "pf_big_bb": 3.0,          # a preflop raise to this many big blinds counts as a big bet
    "value_edge": 0.12,        # preflop: raise to the max when its edge is this share of the raise
    "allin_margin": 0.03,      # call a preflop all-in with equity this far above the pot odds
    "sticky_fold": 0.35,       # postflop fold-to-bet rate at and above which a seat gets no special treatment
    "sticky_value": 0.52,      # value-bet threshold against a seat that never folds
    "sticky_allin": 0.70,      # get it all in postflop with this equity against a seat that never folds
    # Layer 2: every count above is read with old hands faded, and raise ranges widened for seats that raise at random.
    "half_life": 150.0,        # hands for an observation's weight to halve, so a change of style is re-read
    "shown_prior": 3.0,        # showdowns of a seat whose raises mean strength, behind the random-or-strategic read
    "random_gap": 0.5,         # raises read as fully random once the shown raise-call strength gap falls to this share of a strategic seat's
    "trials": 40,              # Monte Carlo rollouts per postflop decision
    "decision_ms": 0.6,        # stop rolling out after this long
    "round_budget_s": 1.2,     # own thinking time after which rollouts are cut to a quarter
    "round_stop_s": 2.5,       # own thinking time after which only a handful of rollouts run: the tournament also counts transport
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


class Seat:
    """Running counts of what one opponent does."""

    __slots__ = ("hands", "vpip", "pfr", "shove", "bets", "passive", "folds", "continues",
                 "pf_faced", "pf_called", "shove_faced", "shove_called")

    def __init__(self):
        self.hands = self.vpip = self.pfr = self.shove = 0
        self.bets = self.passive = self.folds = self.continues = 0
        self.pf_faced = self.pf_called = self.shove_faced = self.shove_called = 0


class Track(Seat):
    """Seat's counts, each hand weighted 2 ** (hand / half_life) so old hands fade without rescaling any count, plus
    what the random-or-strategic read needs: pfr and shove before widening, the preflop hand_pct shown at showdown
    after raising and after only calling ([raises, their pct sum, calls, their pct sum]), and how random raises look."""

    __slots__ = ("pfr_own", "shove_own", "shown", "rnd")

    def __init__(self):
        Seat.__init__(self)
        self.pfr_own = self.shove_own = self.rnd = 0.0
        self.shown = [0.0, 0.0, 0.0, 0.0]


class Agent:
    def __init__(self, params=None):
        self.p = dict(PARAMS, **(params or {}))
        self.rng = random.Random()
        self.seats = []
        self.hand = 0
        self.w = 1.0  # weight of the latest hand's counts
        self.stack = 2000
        self.bb = 20
        self.spent = 0.0
        gc.disable()  # a collection pause can blow the 10 ms limit

    def on_table_start(self, info):
        self.seats = [Track() for _ in range(info["num_players"])]
        self.stack = info["starting_stack"]
        self.bb = info.get("big_blind", 20)

    # ------------------------------------------------------------ profiling
    def _rate(self, count, total, prior, k=None):
        """A seat's count / total shrunk toward prior by k hands; k is scaled to the counts' current hand weight."""
        k = (self.p["prior_hands"] if k is None else k) * self.w
        return (count + prior * k) / (total + k)

    def _pf_call(self, s):
        """Chance a seat calls a preflop all-in: its rate against all-ins, starting from its rate against big raises."""
        k = self.p["sticky_prior"]
        big = self._rate(s.pf_called, s.pf_faced, self.p["prior_pfcall"], k)
        return self._rate(s.shove_called, s.shove_faced, big, k)

    def _fold_fast(self, s):
        return self._rate(s.folds, s.folds + s.continues, self.p["prior_fold"], self.p["sticky_prior"])

    def _sticky(self, s):
        """0 for a seat that folds to bets normally, 1 for one that never folds."""
        return max(0.0, 1.0 - self._fold_fast(s) / self.p["sticky_fold"])

    def _seat(self, i):
        while len(self.seats) <= i:
            self.seats.append(Track())
        return self.seats[i]

    def on_hand_end(self, summary):
        t0 = time.perf_counter()
        p = self.p
        n = len(summary["stacks"])
        self._seat(n - 1)
        self.hand += 1
        self.w = w = 2.0 ** (self.hand / p["half_life"])
        big = p["big_bet"] * self.stack
        pf_big = p["pf_big_bb"] * self.bb
        entered, raised, shoved = set(), set(), set()
        street, bet_open, put, top = "preflop", False, [0] * n, 0
        for h in summary["history"]:
            a, i, amount = h["action"], h["seat"], h["amount"]
            if h["street"] != street:
                street, bet_open = h["street"], False
            if a in ("small_blind", "big_blind"):
                put[i] = amount
                top = max(top, amount)
                continue
            s = self.seats[i]
            if street == "preflop":
                if top >= pf_big and put[i] < top:
                    s.pf_faced += w
                    s.pf_called += w * (a != "fold")
                    if top >= big:
                        s.shove_faced += w
                        s.shove_called += w * (a != "fold")
                if a == "raise":
                    put[i] = top = max(top, amount)
                elif a == "call":
                    put[i] += amount
                if a in ("call", "raise"):
                    entered.add(i)
                if a == "raise":
                    raised.add(i)
                    if amount >= big:
                        shoved.add(i)
                continue
            if bet_open:
                if a == "fold":
                    s.folds += w
                else:
                    s.continues += w
            if a == "raise":
                s.bets += w
                bet_open = True
            elif a in ("check", "call"):
                s.passive += w
        for k, cards in summary.get("shown", {}).items():
            i = int(k)
            if i < n and (i in raised or i in entered):
                s = self.seats[i]
                j = 0 if i in raised else 2
                s.shown[j] += w
                s.shown[j + 1] += w * hand_pct(card(cards[0]), card(cards[1]))
                s.rnd = self._random(s)
        for i in range(n):
            s = self.seats[i]
            s.hands += w
            if i in entered:
                s.vpip += w
                if i in raised:
                    s.pfr_own += w
                    if i in shoved:
                        s.shove_own += w
            r = s.rnd
            s.pfr = s.pfr_own + r * max(0.0, s.vpip - s.pfr_own) if r else s.pfr_own
            s.shove = s.shove_own + r * max(0.0, s.vpip - s.shove_own) if r else s.shove_own
        self.spent += time.perf_counter() - t0

    def _random(self, s):
        """0 for a seat whose shown raises are stronger than its shown calls as a strategic seat's are, 1 for one
        whose raises show no stronger hands; its raise and shove ranges are widened toward its entering one by this."""
        p = self.p
        sh, k = s.shown, p["shown_prior"] * self.w
        if sh[0] < 0.5 * self.w:
            return 0.0
        pr = self._rate(s.pfr_own, s.hands, p["prior_pfr"])
        vp = self._rate(s.vpip, s.hands, p["prior_vpip"])
        # A strategic seat shows raises from its top pfr share and calls from the band below, vpip / 2 apart.
        gap = (sh[3] + k * (pr + vp) / 2) / (sh[2] + k) - (sh[1] + k * pr / 2) / (sh[0] + k)
        return min(1.0, max(0.0, 1.0 - gap / (p["random_gap"] * vp / 2)))

    # --------------------------------------------------------------- acting
    def act(self, state):
        t0 = time.perf_counter()
        try:
            if state["street"] == "preflop":
                move = self._preflop(state)
            else:
                move = self._postflop(state, t0)
        except Exception:
            move = self._passive(state)
        self.spent += time.perf_counter() - t0
        return move

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
        return {"action": "raise", "amount": max(lo, min(target, hi))}

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
        committed = raises and (top_bet >= p["big_bet"] * self.stack or to_call >= 0.3 * self.stack)
        if committed:
            # Equity against the raiser's estimated range (and each caller holding the same) against the pot odds.
            eq = range_equity(TABLE, WEIGHTS, cls, self._raise_width(raiser, raises, top_bet)) ** (1 + callers_of_raise)
            if eq >= to_call / (state["pot"] + to_call) + p["allin_margin"] - p["risk"]:
                return {"action": "all_in"}
            return self._passive(state)
        if "raise" in state["legal_actions"] and self._value_edge(state, cls, raised, entered) >= p["value_edge"]:
            return {"action": "raise", "amount": state["max_raise_to"]}

        if raises == 0:
            behind = (state["button"] - me) % n
            behind = 1 if behind == n - 1 else 0 if behind == n - 2 else behind + 2
            limit = p["iso_raise"] if behind == 0 else p["open"].get(behind, 0.12)
            if pct <= limit:
                return self._raise(state, (p["open_bb"] + limpers) * bb)
            return self._passive(state)

        width = self._raise_width(raiser, raises, top_bet)
        depth = pct / width  # 0 = top of the raiser's range, 1 = its bottom
        crowd = 0.7 ** callers_of_raise  # callers behind a raise hold real hands too
        if depth <= p["threebet_r"] * crowd:
            return self._raise(state, top_bet * 3 + to_call * callers_of_raise)
        cheap = to_call <= p["setmine_cost"] * self.stack
        if cheap and (c1 >> 2) == (c2 >> 2):
            return self._call(state)
        if to_call <= 0.08 * self.stack and pct <= min(p["call_r"] * width, p["call_cap"]):
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

    def _value_edge(self, state, cls, raised, entered):
        """Expected gain of raising to the max, per chip raised, if it is called: each live seat calls at its
        call-big-bet rate with that top share of what it holds; multiway equity is the product of heads-up ones."""
        p = self.p
        me = state["seat"]
        dp, q = [1.0], [1.0]  # by number of callers: sum of P(callers) * equity, and P(callers)
        for i, f in enumerate(state["folded"]):
            if f or i == me:
                continue
            s = self._seat(i)
            c = self._pf_call(s)
            if i in raised:
                held = self._rate(s.pfr, s.hands, p["prior_pfr"])
            elif i in entered:
                held = self._rate(s.vpip, s.hands, p["prior_vpip"])
            else:
                held = 1.0
            e = range_equity(TABLE, WEIGHTS, cls, max(0.02, c * held))
            ndp, nq = [0.0] * (len(dp) + 1), [0.0] * (len(q) + 1)
            for k in range(len(dp)):
                ndp[k] += dp[k] * (1.0 - c)
                ndp[k + 1] += dp[k] * c * e
                nq[k] += q[k] * (1.0 - c)
                nq[k + 1] += q[k] * c
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

        if to_call == 0:
            # A seat that never folds pays off thinner value and bigger bets, and is never bluffed.
            sticky = max(self._sticky(self._seat(i)) for i in live) if live else 0.0
            frac = p["bet_frac"] + sticky * (1.0 - p["bet_frac"])
            if sticky >= 0.5 and eq >= p["sticky_allin"] and "raise" in state["legal_actions"]:
                return {"action": "raise", "amount": state["max_raise_to"]}
            if eq >= p["big_value"]:
                return self._raise(state, max(bets) + max(p["big_bet_frac"], frac) * pot)
            if eq >= p["value"] - sticky * (p["value"] - p["sticky_value"]):
                return self._raise(state, max(bets) + frac * pot)
            if len(live) == 1 and me in raised_pre and sticky == 0.0:
                s = self._seat(live[0])
                fold_rate = self._rate(s.folds, s.folds + s.continues, p["prior_fold"])
                if fold_rate >= p["bluff_fold_rate"] and self.rng.random() < p["bluff_freq"]:
                    return self._raise(state, max(bets) + frac * pot)
            return self._passive(state)

        odds = to_call / (pot + to_call)
        s = self._seat(bettor) if bettor >= 0 else Seat()
        if (bettor >= 0 and self._sticky(s) >= 0.5 and eq >= p["sticky_allin"]
                and "raise" in state["legal_actions"]):
            return {"action": "raise", "amount": state["max_raise_to"]}
        aggr = self._rate(s.bets, s.bets + s.passive, p["prior_aggr"])
        size = min(1.0, to_call / max(pot - to_call, 1))
        need = odds + p["call_margin"] + p["passive_margin"] * (1.0 - aggr) * size
        if eq >= p["big_value"] + 0.5 * p["passive_margin"] * (1.0 - aggr):
            return self._raise(state, max(bets) + 0.75 * (pot + to_call))
        if eq >= need - p["risk"]:
            return self._call(state)
        return self._passive(state)

    def _equity(self, hero, board, widths, t0):
        """Chance of winning at showdown against one hand per width, each drawn from that top share."""
        p = self.p
        trials = p["trials"] if self.spent < p["round_budget_s"] else p["trials"] // 4 if self.spent < p["round_stop_s"] else 6
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
