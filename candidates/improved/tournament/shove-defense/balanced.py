"""v0 skeleton: the incumbent (VIVelev Monte Carlo, candidates/incumbent/bot.py) refactored into hooks.

Behaviour is intended to match the incumbent exactly except for the safety layer:
  * every returned action passes `sanitize()` (legal action, int raise-to clamped to [min, max]);
  * every exception falls back to check/fold.
Tournament solvers change ONLY the hook(s) they are assigned (search for `HOOK:`), so that winners merge cleanly.

Official API (inferred from the incumbent): Agent() with no args, optional on_table_start(info), act(state).
Known state keys: hole_cards, board, legal_actions, min_raise_to, max_raise_to, folded, seat.
Other keys (pot, to_call, stacks, bets, button, street, big_blind, history) are read through S() with fallbacks,
because the official names are not confirmed yet. Keep all key access going through S().
"""
import random
import time

MAX_SAMPLES = 32
THINK_SECONDS = 0.0012
RANKS = "23456789TJQKA"
SUITS = "shdc"


# ---------------------------------------------------------------------------
# State access (single place to adapt key names once the official format is confirmed)
# ---------------------------------------------------------------------------
_ALIASES = {
    "hole_cards": ("hole_cards", "hole"),
    "legal_actions": ("legal_actions", "legal"),
    "pot": ("pot", "pot_size"),
    "to_call": ("to_call", "amount_to_call", "call_amount"),
    "stacks": ("stacks", "stack_sizes"),
    "bets": ("bets", "street_bets", "committed"),
    "button": ("button", "dealer", "button_seat"),
    "street": ("street", "round"),
    "big_blind": ("big_blind", "bb"),
    "history": ("history", "action_history", "actions"),
}


def S(state, key, default=None):
    for k in _ALIASES.get(key, (key,)):
        if k in state and state[k] is not None:
            return state[k]
    return default


def _card(text):
    return RANKS.index(text[0].upper()) * 4 + SUITS.index(text[1].lower())


def _straight(mask):
    consecutive = mask & (mask >> 1) & (mask >> 2) & (mask >> 3) & (mask >> 4)
    if consecutive:
        return consecutive.bit_length() + 3
    return 3 if mask & 0x100F == 0x100F else -1


def _kickers(mask, count):
    result = 0
    shift = 16
    for _ in range(count):
        rank = mask.bit_length() - 1
        result |= rank << shift
        mask ^= 1 << rank
        shift -= 4
    return result


def _evaluate(cards):
    """Best-five evaluator for 5-7 distinct cards; higher wins."""
    ranks = pairs = trips = quads = 0
    suits = [0, 0, 0, 0]
    for card in cards:
        bit = 1 << (card >> 2)
        quads |= trips & bit
        trips |= pairs & bit
        pairs |= ranks & bit
        ranks |= bit
        suits[card & 3] |= bit
    flush = 0
    for suited in suits:
        if suited.bit_count() >= 5:
            straight = _straight(suited)
            if straight >= 0:
                return (8 << 20) | (straight << 16)
            flush = suited
            break
    if quads:
        rank = quads.bit_length() - 1
        return (7 << 20) | (rank << 16) | (_kickers(ranks ^ (1 << rank), 1) >> 4)
    if trips:
        rank = trips.bit_length() - 1
        other_pairs = pairs & ~(1 << rank)
        if other_pairs:
            return (6 << 20) | (rank << 16) | ((other_pairs.bit_length() - 1) << 12)
    if flush:
        return (5 << 20) | _kickers(flush, 5)
    straight = _straight(ranks)
    if straight >= 0:
        return (4 << 20) | (straight << 16)
    if trips:
        return (3 << 20) | (rank << 16) | (_kickers(ranks ^ (1 << rank), 2) >> 4)
    if pairs:
        high = pairs.bit_length() - 1
        rest = pairs ^ (1 << high)
        if rest:
            low = rest.bit_length() - 1
            remaining = ranks & ~(1 << high) & ~(1 << low)
            return (2 << 20) | (high << 16) | (low << 12) | (_kickers(remaining, 1) >> 8)
        return (1 << 20) | (high << 16) | (_kickers(ranks ^ (1 << high), 3) >> 4)
    return _kickers(ranks, 5)


def _remaining_opponents(state):
    return sum(not folded for seat, folded in enumerate(state["folded"]) if seat != state["seat"])


def _estimate_win_rate(hole, board, opponents, rng, deadline=None, max_samples=MAX_SAMPLES):
    """Incumbent statistic: uniform rollouts vs random hands; ties count as wins."""
    if opponents == 0:
        return 1.0, 0
    known = set(hole + board)
    deck = [card for card in range(52) if card not in known]
    missing = 5 - len(board)
    wins = samples = 0
    for _ in range(max_samples):
        if samples and deadline is not None and time.perf_counter() >= deadline:
            break
        draw = rng.sample(deck, missing + 2 * opponents)
        complete = board + draw[:missing]
        score = _evaluate(hole + complete)
        won = True
        for offset in range(missing, len(draw), 2):
            if _evaluate(draw[offset:offset + 2] + complete) > score:
                won = False
                break
        wins += won
        samples += 1
    return wins / samples, samples


# ---------------------------------------------------------------------------
# Safety layer (mandatory for every candidate)
# ---------------------------------------------------------------------------
def safe_default(state):
    legal = S(state, "legal_actions", []) or []
    return {"action": "check"} if "check" in legal else {"action": "fold"}


def sanitize(action, state):
    legal = S(state, "legal_actions", []) or []
    if not isinstance(action, dict) or action.get("action") not in legal:
        # map common mistakes to the closest legal action
        a = action.get("action") if isinstance(action, dict) else None
        if a == "check" and "call" in legal:
            return {"action": "fold"} if "fold" in legal else {"action": "call"}
        if a == "call" and "check" in legal:
            return {"action": "check"}
        if a == "raise" and "call" in legal:
            return {"action": "call"}
        if a == "raise" and "check" in legal:
            return {"action": "check"}
        return safe_default(state)
    if action["action"] == "raise":
        lo, hi = state.get("min_raise_to"), state.get("max_raise_to")
        try:
            amt = int(round(float(action.get("amount", lo))))
        except (TypeError, ValueError):
            amt = lo
        if lo is None or hi is None:
            return safe_default(state)
        return {"action": "raise", "amount": int(max(lo, min(hi, amt)))}
    return {"action": action["action"]}


# ---------------------------------------------------------------------------
# Opponent stats tracker (shared, minimal; HOOK: opponent_model may replace/extend)
# ---------------------------------------------------------------------------
class OpponentStats:
    """Counts per seat from observed public events. Robust to missing/odd events."""

    def __init__(self):
        self.seats = {}
        self._hand = None
        self._street = None
        self._vpip_done = set()
        self._facing_bet = False

    def _s(self, seat):
        return self.seats.setdefault(seat, {"hands": 0, "vpip": 0, "pfr": 0, "shove_pf": 0,
                                            "fold_vs_bet": 0, "faced_bet": 0, "bets_raises": 0,
                                            "calls": 0, "showdowns": []})

    def observe(self, ev):
        try:
            t = ev.get("type")
            if t == "hand_start":
                self._hand = ev.get("hand_id")
                self._vpip_done = set()
                self._street = "preflop"
                self._facing_bet = False
                for s in range(len(ev.get("stacks", []))):
                    self._s(s)["hands"] += 1
            elif t == "board":
                self._street = ev.get("street")
                self._facing_bet = False
            elif t == "action":
                seat, a = ev.get("seat"), ev.get("action")
                st = self._s(seat)
                street = ev.get("street", self._street)
                if a == "post":
                    return
                if self._facing_bet and a in ("fold", "call", "raise"):
                    st["faced_bet"] += 1
                    st["fold_vs_bet"] += a == "fold"
                if a in ("call", "raise") and street == "preflop" and seat not in self._vpip_done:
                    st["vpip"] += 1
                    self._vpip_done.add(seat)
                if a == "raise":
                    st["bets_raises"] += 1
                    self._facing_bet = True
                    if street == "preflop":
                        st["pfr"] += 1
                        if (ev.get("amount") or 0) >= 1900:
                            st["shove_pf"] += 1
                elif a == "call":
                    st["calls"] += 1
            elif t == "showdown":
                for seat, cards in (ev.get("hands") or {}).items():
                    self._s(int(seat))["showdowns"].append(list(cards))
                    self._s(int(seat))["showdowns"] = self._s(int(seat))["showdowns"][-50:]
        except Exception:
            pass

    def rate(self, seat, num, den, prior=0.0, k=10):
        st = self.seats.get(seat)
        if not st:
            return prior
        return (st[num] + prior * k) / (st[den] + k)


# ---------------------------------------------------------------------------
# HOOKS — default implementations reproduce the incumbent. Return None to defer to the incumbent policy.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# shove-defense (balanced): fixed, non-adaptive calling rule when facing an all-in / stack-sized bet.
#
# Preflop: equity of our 169-class hand vs a FIXED mixture model of the jammer's range, of the ranges of
# players who already called, and of possible overcallers behind, using an embedded equity table
# (C Monte Carlo, 6000 samples/entry). Hands are ordered by equity vs one random hand; the table holds
# equity vs every multiset (size 1..3) of four primitive ranges: top 100% / 40% / 15% / 5%.
# Because equity is linear in each opponent's hand distribution, equity vs a mixture of primitives is the
# weighted sum of the table entries. Call iff EV(call) > 0 (EV averaged over overcalls from behind).
# Postflop: small Monte Carlo with the skeleton evaluator vs (random | made-hand) mixture ranges.
# All strategy claims here are hypotheses until the arena confirms them.
# ---------------------------------------------------------------------------
#
# The encoded table: _SD_RAW[key] is 169 x 3-digit equities (x1000) in _SD_ORDER, key = sorted range ids
# ('0'=top100%, '1'=top40%, '2'=top15%, '3'=top5%), one digit per opponent.
_SD_ORDER = "AA KK QQ JJ TT 99 88 AKs 77 AQs AJs AKo AQo ATs AJo KQs 66 A9s ATo KJs A8s KTs KQo 55 A7s KJo A9o K9s A6s A5s QJs A8o KTo QTs A4s A7o QJo K8s A6o A3s K9o A5o JTs K7s A2s Q9s QTo A4o 44 K6s K8o A3o J9s K5s JTo Q8s K7o K4s A2o Q9o Q6s K3s J8s Q7s K6o 33 K5o K2s T9s Q8o J9o J7s Q5s T8s Q7o K4o Q4s T9o J8o Q6o K3o T7s Q3s K2o 22 J6s 98s Q2s Q5o J5s J7o T8o J4s 97s T6s Q4o Q3o 98o J3s 87s T7o J6o J5o J2s 96s T5s Q2o T4s 86s J4o T6o 97o 95s T3s 76s J3o 87o T2s J2o T5o 96o 85s 75s 94s T4o 86o 65s 93s 76o 84s 92s T3o 74s 95o T2o 54s 64s 85o 94o 73s 83s 82s 75o 65o 93o 84o 63s 53s 92o 43s 74o 72s 54o 52s 62s 64o 83o 82o 73o 42s 32s 53o 63o 43o 52o 72o 62o 42o 32o"
_SD_RAW = {
    "0": "860825804770742719700672662666657657649656628621648630633631627622621591617608604600607613603610596597592592577578578584572581577572573578574567566556558568547554554561555545545550535549541546540540546527525544536514519519507523516509512502517503515497512507505510502500497489487489492481476487474475495486473482476479464473459462470462455450454443462457450440451445438433442440433433415430419435421419419423414409408405407397402408406390397390383380383382381372384379378372368374358366352357342350341352316",
    "1": "859784715694661614593665567638618657626599596554547571586541550519533523538504549496511519478526503464505500450451483501462484447447492439433475512438430472419423406407423420468401384419391401407483391414406382385376376395352391372376357356378391366381464367390373354361344360351379375346344361372397365339323343381364335363391322336354351350390320367351318313346362373341323356396349361361330305362320298377368336309348346348340350312318360366292365322329339342332347305307317341341332323330306290299302309",
    "2": "848733675630581540518625494568525595548483499451472432446418422393420434413393412361399413393392357376404374349357360397323373389347391359354362422342304358368348349353307339368324343324363336312429308327382325334333329359304299310352316291301360330303406318357324294322304327329354343288284324320366317290292322339314296329342284306324326317346287330320281275305333334319283319353316326330303277337292274342342294274318307313308324272286324335279336293318309321312306274274276307305298295288281268270272276",
    "3": "828712617542489426384478327401380453369350336371305329317357321356343312308315292335307322368281322355310265321311278327286278354300310329316282292298265284321296324310269290261296295289315297258299251279336273304280302315258266289293274266247294292244289281303290262283252275276296282258249282281285258246244283275279254266276246249250270259264231246267240240240262267259234248277258239255249223254234221276260225213248237237227244213216259274214258212219243260231229198208204249247234201217205185196211208",
    "00": "732694652612584539502504468497483475465470438481438446442463443450438386420430418420405411448406406422403385426408387397383382422389390404401374362390358366388365379375363363348371360352368354343338349341396351365349355376341337342359336328319350323306317328362319319327316334322334325301296307312341319299301309328315287301314285288302291287315273309282262262281311302281267290297270278280279251287261246293295269246261268255267273237246256266227275254248266255249257229215226251237243232228212202204209200",
    "01": "727652600552503476440489412483450464438437417416385401410407395397399359383371374363370368368355360376359335350327325347327326361331342345340321337317305314336302327321285308306308290302305299284319273291330286296289299318271266283309272260249298270247296287310278251276265280277294289240249287268318261245250262283272229268286234245267269261301226263246234230252282282256234251284256273261247210264237200283276250211247244230246261207224262266198258242233244255242234201192220248239233225228212192206205198",
    "02": "719613568499453414395451372425389420398374364362332333337334316321339317305303288298296321324283289330298279292279257290271257331283277303292248298287245257302268295300244259248258282266298261233274235250308256264276272302237232262280253238222283266218266267294254237240235271250286269214220270250290233215212241275249210250272207220251251240274207252234196219226255265236203243268225233233230200251217199274250223197234225232225236195213244253185251213220228247226223204190201224231218207200188183188201187",
    "03": "705597501442390333297395254335310357311306281326254270255307260309286238255275245270257264325227265310260218282252212268225225304251257290272222229258220219276238272251213239212251237235257244202214207233271229238233243266209206239242217211197237233198215223252233198236193229218240223199202216222240202187189217233225191219221185188196212207227178208203168181182220228199171195237204189200194171217177164228213184151191200188186195162166198225150220169168188187189178148145159193187182165171155134144152150",
    "11": "751642568514472431398482388461428446432417391389377371382364363346349339349339345332331323333327305339318303307297289318289295336285317317296297327287262275310279291280261267273269282265288280243311237255313263272280265294226233261274254233234287258218299262292252232261236265261285281235217261258302254229225240273246217244290218247252254258299218263240210219240259275250220254275240252254236216259214204287274236212250242236231268205221260258200261227231242248240237195201218246231220227227211190208212206",
    "12": "733624555484444400367451342415375429374351348343339321316312302309299319269276279274277277308266273301284253281269239278240241306255269283272239299261229241275255276277224247225244251239259257214294215238287234249259249281221213257250241223200259245189283241280231212241217242241263264210199239238277234211202231260234201239265199219234238235276204237231197204226249268235209248274235250245224195251201196263257218198238237228228235198209243254189250217224236246237237192195205231232215218208198189189214189",
    "13": "728574490419365340286367252322307334281283263304252267240295247277264241241249211265239252291206242280247206258241201227208208285220236259257202240231192207255221252241184225190228233208233235187232185218267202219226237249198187232224204191180231217182225207247221184217182215216245215186189212218240192179184218230210180219231178189200223212238174196201169183186224231197173194246189209194195178210174160235218184159204184183179201156171212219156219177181207209191188147142160213201186169186172137153164166",
    "22": "732593520456408374350417332383321387351299304304317264268291262277273296248247215266237248281225239291251209247250201238208202282237246263256206282239219208272239236253214235193224245229262244215280200230266224224241243273206202242245218218182255232192273225265233202230207236224275242198206234224285216200194229244227191228262189198227237220264182240225178198216248255208190229271215232248221184237198186265263215187216227224215241177199248258189241215211219242230218186193179231239214206219191186187199190",
    "23": "709546482399353308267343237308278322274259234292243226230256229259237231211230191227217222271179219268222161231231163218185181262210207236231181231210188179253215230227172207169205226215229224171222174207247194209215224237174173217223192183178226219161222203229215183201172204212230209179175200212237191170176200211198172201222161177183196205236160197192158160182222223194169193231190192203188164217170157235223177154193191194186206159166209229143214167182203206194185151143153204200182181177177140159167160",
    "33": "702527433345301260237308220269248274237234212273206213198239214230231200204202172201204228254167197251207167211201164202170183247196204232210181199201156174221199205214155204167197207196210206162198166197222167193198207220162159210203172167150199204151193202200191168198166178193208200170163173188219170153153186187192156187206148158166185186216150187189148152170204209182152170215179177192177140195159135218208155140181169164175184137145192213126192161160196196177178129132140187185169156163154117134151143",
    "000": "632588534503446411379423332406389391367370346387314349347369331356362300318338305324312317354292327347317286331296277314287272335298289318309262266291268267321288308299264280247285275272297273264237250263302255281274275287234244260275254226224271252218219258280249225249226253234266244214207244227267236214210223263230210230252195218234225224262200235215187200202231230220189201234198212224212176215184170233217188172205200181199191166181198216164199185189185196185181157160163195180178166159159141151146146",
    "001": "639553484445412372327399316380353376352342322350283310309331313323301281288286271296284285311250285311272246286269228260256245308261255289266229255252229238279247266271225239223249232239260249220244208226289222246247231262210201226246218194191252228183221230266215185229206225212247230191175229206249213192182208235205174213237184194207220202241168222192166173205219238208165205228187202207182172217176160227215179160196198185184201153168198204148215174191190195192181145142154194187171165178151143154155138",
    "002": "638521468407385341307365291343317337306296294315268265247290245278285265256262214253240242288207238282238206257252199230218206268232220257243202222224204192265215241235201219196220226213232222187219175208260209214228225259188185216234200186166231205163215206250201185207188215204235228174165207202235191169171191219210156198231166173196201188240159215193154160194210225191156193236181198202187151197157145210212175157183181188182186153154207202145201163170184177182170147147149172189170154161143135140140147",
    "003": "621508412366324279245329213298282301263264239278203236218260219262250209212229203231218228275192219262220178237223172216198193268214209241230182201213169187236215224232170204171197203202221205169177169193241177200206202221156161204206179164156212198145182192218200157186166193187204197158151185182214170162155182205184148181192147160176186186202142176164134142159183199168137158203169171176157138181143129205187145126161163160154166130139179183122180128150162165163143124118121170167153132140130105122130113",
    "011": "638540467426393350324375297352342339319330302323283292284302281281284271266267254256254262284233259285252234258239219247226226282242237254235209242224201200259236254242203223203223235205241226178226182203257202215228211252188180209230210179168228216166214219244205175209198212208240219178168216213230196177175200226199162203232174182200212199237166202187153171197229233193165183234186211203193159209177155235220182157206189179189200161170203213153207185177191198185188143151169197192186164172160137146154149",
    "012": "634533468389353315296354273335308308289287275284269250248267241250261249231232211226229226272200220256223196235229189220203191264226218235225185233215173170237209229235175201171208221208229207170225167194248191200226213240182164200215199181158222213152211202240194172208184196193218214165163205196231197164160191213184155208235156182189197195237153200188145156183215225199164186227180191199185149209164151230226176152194181182189192146162205207147202169179189193170171140145152195183164167165161141143155144",
    "013": "615492411351309267242315217282265274251247224269217223197252225248229202209213183219204218255176210245207158227201168203186178233189207219209168199193169164223196225210157197159188196193215195159185155187220174192191196208152152197194172158143202189135178179216180152191153179176202193150156174180208171146151179181181145174191152151160188175202140172174137142149183191170135160198161173170158136177140131197204152132167163159164166122128172189125190142157180177170153122120129175163157143155142107128136129",
    "022": "631509423383328297300329261302277295268258229268246228210255211235239224207209179222205213242180197243209166214220147205175169260216191225206158224207174161222201208222170189150177203199214210167219161195240180185211203221171155197194181170148207188147208189234198160189172187187232214164155191184236178143153171210190146192221159169184192192228145189181143153168208213182149187226180190198172153205154148223218167141186175179188192152166203203139206166180185193182181140136155186177170162167151134144158146",
    "023": "621473398324287252225306201260240271221220198251210209177231196229218201189194156199178201232147187228198146200190139186166153226187186201194148193184153149221179194207151179142178197183200191156182145175219159171198189204152139194177153150138190187133187178209177151176147178174198189151139165177201164142137178183177124168193132144156168167207134169171123148153180206157132160210149172171155134178139122206198150132170159161165177134139177194115176145146166182162159117121122169164158141150137112131134124",
    "033": "590438346294254219197264179241230231216210176232180192164209175221196170176177144187177195227136164225186132192182130185144151207169173201181150170168133156190176179194135173143173180166182183137168129172204148160176175190133126182180151150126182172122158173187168143172136158170180172134131150163194139133129167171173126158196136132148169163194122158161120124146168187163123147198151154162140120173124123191185135119153148145152163106127179176114176136137147161157151109106117162162148125143134090118130119",
    "111": "651544455406374335312372289344325335313312300299286279262273272272261256252240233249240248280223241265239212243225209234210209263225231256231194245221197187249218233236182204186213220196222218170240170196259195209230213228182161211208185181152229204161229217252192163201180204198237216167163201189247195173161204227203159200235168183207209187243156209203159166186220227194164210247194203209184154220171169237231183158201189188205199162171222223143215177187197206197187152145164194197194183185170145162168159",
    "112": "645532448390348314300355283316296305287273253276262241231266236251243251216217197223216217242176204247218174222212165222188175251214213236215169228203166170228205224219168201171192216188222219168218158185244179202211207236178155201206179172146218197146201209235190160196176197194223209161153193194238185153155185232196149195226156172193197183233155195189152158186210225182164190241182201201182153198162143236224174149190179192197206153168216215146210176173189201202186149146163200193184173177160148152156159",
    "113": "619494403359315266236310219270253259238228203252223212195236209235211213191196165196190200249163195231204149202193157188165161233188191219195157208183158158217185199204141173151180196178190191149192145176216155172183183206150144186178167155137195190130181179204173144185155171172197192152139171179199153145139174190174129169196146150168190170211142165171128140159190199165135160215172165178164136181139133208207147127178167164168183128148185198125196147157174172171168120126137176167162153160150109128149137",
    "122": "640526429373321286278331260290259290252244220267250213192238201230235225200199168214185204236163190229213154206213151186171158233193184222206153225202161158225195201205163183138179191183214201152221156172223178173199194228162151191199173166138204188137210191230187164187164185186217198155143195182229177153152187217199147190227152162181193187232137207186138155167205224187150195232184195199169148204165142231223181152193184188187204141166218220137204182182192190191181156150147193190183175172166140155162154",
    "123": "629474408333285250230290208257236242214213190240207185178215192217214199168180148187180177221138178226180133198185137185154142222186181200191148189171151139201178184196134173139162180165195186138193139170212155169181183203147130174167158157131188170120185185208175147166147168182198181133146160173190147138133162189170127176192132145152178167203130166154129138156190197158135168222163178173160136191142129198199161129171166150162179124142185201120191157154181185169166122113130170175168144162146122142140135",
    "133": "599451352295252226199263184230207228199202173220189175152199171210181176170169142179168182221128162220171121185157129179143147203165175190169131178160119138191171178177123164136158177166175168132177124163194136158175185185133127181164139149113181174113167164190163142172129150161174180135131145153190137122131156180157122168183131132147165157196116156160122131137174192153131145207152156165145117181124117196194146117161155145163170116122182185117188142145167170168155110103118179160163134149135104126135131",
    "222": "634520426354317289276304244276239264236217188236233193177229186211207234179185150184175193213152176223179139191191132176142142222185180204190140227184157134204182186210151192136163193184202197158215139173222165173196186224152145180184163154141212187140209186219190146184156181185209197160152175173232177144140176197187137186217144162172187181227148193179146148164205221181144192235171201197178145204146136226221175134195187183177195137164200217134209176183190200184181142145163188187179172172159141158153160",
    "223": "612471389320267242220272205238215232199190175222191165157213167202188197167170135176157177206126155210173125181175114180136138197162160195175136189174138129189171175185132170128150182164197174137182129161206154146177182203142135173160143137125191173126181172194163143172138164168194179136143162162221149128133158173171134171201129148156177170209124177155117132151192197163137171209165180174167133185134128205197154124181161156167186124131186203122194144153177188174174131121137177171162152156139113142141134",
    "233": "588425353282250221196254181222199209172184154203176167148192157190169185155153119167149185199116148193166111167161117163125131185158162182162129179161130126180159157181115159117144174157179164124174123149188141147177178178125128170154144136123176164111164163190161145162122144166190160134123151157193137121126146174161130162186126131145169159201122153151118127141172184148120148193149145167135121183128120208185136110154150146149165108117183199108185139140165169166167113108123175160154141156140101133131134",
    "333": "570389322256222190174225164204178191168166143183166149130165155178156167153140108162148170192103140196161109155144114170113130190139160173148135167151109119175157151169105148123136159149168158111155114142180126128151173167118109165149121131100162159100149150174158119159124134150170171123121128152183131113111147173145118161179120122136161149195108143142101116128165190158118135203139154148146112169113103198187133106155143134146160106116171178101183142132163173160153102101111168164156143148133096121131133",
}

_SD_IDX = {h: i for i, h in enumerate(_SD_ORDER.split())}
_SD_EQ = {k: [int(v[i:i + 3]) / 1000.0 for i in range(0, len(v), 3)] for k, v in _SD_RAW.items()}

# Fixed range mixtures (weights over primitives 0..3). Hypothesis: conditional on FACING a jam, the jammer is
# most often a frequent (near-random) jammer, because frequent jammers generate most of the jams we face.
_SD_MIX_OPEN_JAM = (0.75, 0.08, 0.08, 0.09)   # jam is the first raise of the hand
_SD_MIX_REJAM = (0.50, 0.10, 0.17, 0.23)      # jam (or stack-sized raise) over an earlier raise
_SD_MIX_CALLER = (0.25, 0.35, 0.22, 0.18)     # someone who already called the jam / will overcall it
_SD_Q_BEHIND = 0.11                            # P(a player still to act overcalls)
_SD_Q_RAISER_BEHIND = 0.30                     # P(an earlier raiser still to act calls the jam)
_SD_MARGIN = 0.0                               # extra EV margin (fraction of the call) required
_SD_POST_SAMPLES = 120
_SD_POST_W_JAMMER = 0.30                       # postflop: P(jammer's hand is random) vs made-hand range
_SD_POST_W_CALLER = 0.10
_SD_POST_BUDGET = 0.007                        # seconds of postflop Monte Carlo (min 30 samples)


def _sd_class(hole_strs):
    r = "23456789TJQKA"
    a, b = hole_strs[0], hole_strs[1]
    ra, rb = a[0].upper(), b[0].upper()
    if r.index(ra) < r.index(rb):
        ra, rb, a, b = rb, ra, b, a
    if ra == rb:
        return ra + rb
    return ra + rb + ("s" if a[1].lower() == b[1].lower() else "o")


def _sd_eq_set(idx, mixes):
    """Equity of hand index `idx` vs independent opponents, each a mixture over the 4 primitives."""
    n = len(mixes)
    if n == 0:
        return 1.0
    if n > 3:
        # extrapolate: eq_n ~ eq_3 * (eq_3 / eq_2) ** (n - 3), using the three tightest-looking opponents
        e3 = _sd_eq_set(idx, mixes[:3])
        e2 = _sd_eq_set(idx, mixes[:2])
        ratio = min(1.0, e3 / e2) if e2 > 0 else 0.5
        return e3 * ratio ** (n - 3)
    total = 0.0
    if n == 1:
        m0 = mixes[0]
        for a in range(4):
            if m0[a]:
                total += m0[a] * _SD_EQ[str(a)][idx]
        return total
    if n == 2:
        m0, m1 = mixes
        for a in range(4):
            if not m0[a]:
                continue
            for b in range(4):
                if m1[b]:
                    key = "".join(sorted(str(a) + str(b)))
                    total += m0[a] * m1[b] * _SD_EQ[key][idx]
        return total
    m0, m1, m2 = mixes
    for a in range(4):
        if not m0[a]:
            continue
        for b in range(4):
            if not m1[b]:
                continue
            wab = m0[a] * m1[b]
            for c in range(4):
                if m2[c]:
                    key = "".join(sorted(str(a) + str(b) + str(c)))
                    total += wab * m2[c] * _SD_EQ[key][idx]
    return total


def _sd_situation(state):
    """Return (jammer, callers, behind, raisers_behind, n_raises_before_jam) for the current street."""
    me = state.get("seat", 0)
    folded = state.get("folded") or []
    n = len(folded)
    bets = S(state, "bets") or [0] * n
    all_in = state.get("all_in") or [False] * n
    stacks = S(state, "stacks") or [0] * n
    hist = S(state, "history") or []
    street = S(state, "street") or ("preflop" if not state.get("board") else None)
    raises = []
    for ev in hist:
        if isinstance(ev, dict) and ev.get("action") == "raise" and (street is None or ev.get("street") == street):
            raises.append(ev.get("seat"))
    cur = max(bets) if bets else 0
    jammer = raises[-1] if raises else None
    if jammer is None or jammer == me or not (0 <= jammer < n):
        cands = [i for i in range(n) if i != me and not folded[i] and bets[i] == cur]
        jammer = cands[0] if cands else None
    n_before = max(0, len(raises) - 1)
    earlier_raisers = set(s for s in raises[:-1] if s is not None)
    callers, behind, raisers_behind = [], [], []
    for i in range(n):
        if i == me or i == jammer or folded[i]:
            continue
        if bets[i] >= cur or all_in[i] or stacks[i] == 0:
            callers.append(i)
        elif i in earlier_raisers:
            raisers_behind.append(i)
        else:
            behind.append(i)
    return jammer, callers, behind, raisers_behind, n_before


def _sd_preflop(agent, state, ctx):
    legal = S(state, "legal_actions", []) or []
    hole = S(state, "hole_cards")
    idx = _SD_IDX.get(_sd_class(hole))
    if idx is None:
        return None
    me = state.get("seat", 0)
    stacks = S(state, "stacks")
    bets = S(state, "bets")
    to_call = S(state, "to_call", 0) or 0
    pot = S(state, "pot")
    if pot is None:
        pot = sum(bets) if bets else 0
    my_stack = stacks[me] if stacks else to_call
    call_amt = min(to_call, my_stack) if my_stack else to_call
    jammer, callers, behind, raisers_behind, n_before = _sd_situation(state)
    jam_mix = _SD_MIX_OPEN_JAM if n_before == 0 else _SD_MIX_REJAM
    base = [jam_mix] + [_SD_MIX_CALLER] * len(callers)
    cur = max(bets) if bets else to_call
    # overcall events from behind: probability per player, amount each would add
    others = [(i, _SD_Q_BEHIND) for i in behind] + [(i, _SD_Q_RAISER_BEHIND) for i in raisers_behind]
    probs = [1.0]  # distribution of number of overcallers (cap at 2)
    add_amt = []
    for i, q in others:
        new = [0.0] * min(len(probs) + 1, 3)
        for k, p in enumerate(probs):
            new[k] += p * (1 - q)
            new[min(k + 1, 2)] += p * q
        probs = new
        a = cur - (bets[i] if bets else 0)
        if stacks:
            a = min(a, stacks[i])
        add_amt.append(max(0, a))
    avg_add = (sum(add_amt) / len(add_amt)) if add_amt else 0
    ev = 0.0
    for k, p in enumerate(probs):
        if p <= 0:
            continue
        eq = _sd_eq_set(idx, base + [_SD_MIX_CALLER] * k)
        final_pot = pot + call_amt + k * avg_add
        ev += p * (eq * final_pot - call_amt)
    ctx["sd_ev"] = ev
    # stack-sized raise that is not all-in and we can re-raise: jam the top of our calling range
    if "raise" in legal and state.get("max_raise_to") is not None and ev > 0:
        eq_hu = _sd_eq_set(idx, base)
        if eq_hu >= 0.62:
            return {"action": "raise", "amount": int(state["max_raise_to"])}
    if ev > _SD_MARGIN * call_amt and "call" in legal:
        return {"action": "call"}
    return {"action": "check"} if "check" in legal else {"action": "fold"}


def _sd_strong(hole2, board):
    """Made-hand filter on the current board: two pair+, or a pair using a hole card at/above 2nd board rank,
    or a flush draw (4 to a suit using a hole card)."""
    v = _evaluate(hole2 + board)
    cat = v >> 20
    if cat >= 2:
        # discount board-only two pair/trips: require a hole card to matter
        bv = _evaluate(board) if len(board) >= 5 else -1
        return v != bv
    if cat == 1:
        pr = (v >> 16) & 15
        brs = sorted((c >> 2 for c in board), reverse=True)
        uses_hole = any((c >> 2) == pr for c in hole2)
        return uses_hole and len(brs) >= 2 and pr >= brs[1]
    suits = [c & 3 for c in board]
    for c in hole2:
        if suits.count(c & 3) + sum(1 for d in hole2 if d & 3 == c & 3) >= 4:
            return True
    return False


def _sd_postflop(agent, state, ctx):
    legal = S(state, "legal_actions", []) or []
    hole, board = ctx["hole"], ctx["board"]
    me = state.get("seat", 0)
    stacks = S(state, "stacks")
    to_call = S(state, "to_call", 0) or 0
    pot = S(state, "pot")
    bets = S(state, "bets")
    if pot is None:
        pot = sum(bets) if bets else to_call
    my_stack = stacks[me] if stacks else to_call
    call_amt = min(to_call, my_stack) if my_stack else to_call
    jammer, callers, behind, raisers_behind, _ = _sd_situation(state)
    opp_w = [_SD_POST_W_JAMMER] + [_SD_POST_W_CALLER] * len(callers)  # P(hand is random) vs made-hand range
    opp_w = opp_w[:4]
    # private RNG (do not consume the shared agent.rng stream used by the default policy)
    rng = random.Random(hash((tuple(hole), tuple(board), call_amt, pot)) & 0xFFFFFFFF)
    known = set(hole + board)
    deck = [c for c in range(52) if c not in known]
    missing = 5 - len(board)
    share = 0.0
    nsamp = 0
    deadline = time.perf_counter() + _SD_POST_BUDGET
    for _ in range(_SD_POST_SAMPLES):
        if nsamp >= 30 and time.perf_counter() > deadline:
            break
        avail = deck[:]
        rng.shuffle(avail)
        pos = 0
        opps = []
        ok = True
        for w in opp_w:
            if rng.random() < w:
                opps.append(avail[pos:pos + 2])
                pos += 2
            else:
                got = None
                for _try in range(12):
                    if pos + 2 > len(avail):
                        break
                    h2 = avail[pos:pos + 2]
                    if _sd_strong(h2, board):
                        got = h2
                        pos += 2
                        break
                    # recycle: move the rejected pair to the end so cards stay available
                    avail.append(avail.pop(pos))
                    avail.append(avail.pop(pos))
                if got is None:
                    got = avail[pos:pos + 2]
                    pos += 2
                opps.append(got)
        if pos + missing > len(avail):
            continue
        complete = board + avail[pos:pos + missing]
        hs = _evaluate(hole + complete)
        best, ties, mine = hs, 1, True
        for o in opps:
            v = _evaluate(o + complete)
            if v > best:
                best, mine, ties = v, False, 1
            elif v == best:
                ties += 1
        if mine:
            share += 1.0 / ties
        nsamp += 1
    if not nsamp:
        return None
    eq = share / nsamp
    need = call_amt / (pot + call_amt) if pot + call_amt > 0 else 0.5
    need += 0.03 * len(behind) + 0.06 * len(raisers_behind)
    ctx["sd_eq"] = eq
    if "raise" in legal and state.get("max_raise_to") is not None and eq >= 0.70:
        return {"action": "raise", "amount": int(state["max_raise_to"])}
    if eq >= need and "call" in legal:
        return {"action": "call"}
    return {"action": "check"} if "check" in legal else {"action": "fold"}


def hook_facing_allin(agent, state, ctx):
    """HOOK: facing_allin — balanced shove-defense (fixed range model, no per-opponent adaptation)."""
    try:
        if not ctx.get("board"):
            return _sd_preflop(agent, state, ctx)
        return _sd_postflop(agent, state, ctx)
    except Exception:
        return None


def hook_preflop(agent, state, ctx):
    """HOOK: preflop — preflop decisions other than facing all-in."""
    return None


def hook_betting(agent, state, ctx):
    """HOOK: betting — postflop when nothing to call (to_call == 0): check, value bet or bluff.
    Use agent.size(state, ctx, intent, default_frac) for amounts."""
    return None


def hook_facing_bet(agent, state, ctx):
    """HOOK: facing_bet — postflop when facing a bet/raise that is NOT (near) all-in: fold/call/raise."""
    return None


def hook_sizing(agent, state, ctx, intent):
    """HOOK: sizing — given intent in {'value','thin_value','bluff','probe','raise_value','raise_bluff'},
    return a raise-to total (int) or None to use the default pot fraction."""
    return None


def pot_raise_to(state, frac):
    """Raise-to total for a bet/raise of `frac` x pot (pot measured after calling). Falls back to min raise."""
    bets = S(state, "bets")
    pot = S(state, "pot")
    to_call = S(state, "to_call", 0) or 0
    lo = state.get("min_raise_to")
    if bets is None or pot is None:
        return lo
    return int(max(bets) + frac * (pot + to_call))


# Extra per-solver trackers: append a class with observe(event) (and anything else) in YOUR section;
# the Agent instantiates each one and feeds it every event: self.trackers[cls.__name__].
EXTRA_TRACKERS = []


def incumbent_policy(win_rate, state):
    legal = S(state, "legal_actions", [])
    if win_rate > 0.75 and "raise" in legal:
        bound = "max_raise_to" if win_rate > 0.85 else "min_raise_to"
        return {"action": "raise", "amount": int(state[bound])}
    if win_rate > 0.5 and "call" in legal:
        return {"action": "call"}
    if "check" in legal:
        return {"action": "check"}
    return {"action": "fold"}


class Agent:
    def __init__(self, *args, **kwargs):
        self.on_table_start({})

    def on_table_start(self, info):
        info = info or {}
        self.seat = int(info.get("seat", 0) or 0)
        self.rng = random.Random(2018 + self.seat)
        self.last_samples = 0
        self.stats = OpponentStats()
        self.trackers = {}
        for cls in EXTRA_TRACKERS:
            try:
                self.trackers[cls.__name__] = cls()
            except Exception:
                pass
        self.info = dict(info)

    def size(self, state, ctx, intent, default_frac):
        amt = hook_sizing(self, state, ctx, intent)
        return int(amt) if amt is not None else pot_raise_to(state, default_frac)

    def observe(self, event):
        self._observe_seen = True
        self._feed(event)

    def _feed(self, event):
        self.stats.observe(event)
        for t in self.trackers.values():
            try:
                t.observe(event)
            except Exception:
                pass

    # --- kit event layer (AlgoSoc kit calls act() and on_hand_end(); never observe()) ---------------
    def _kit_new_hand(self, hid, n_seats):
        self._hist_hand, self._hist_n, self._hist_k, self._hist_street = hid, 0, 0, "preflop"
        self._feed({"type": "hand_start", "hand_id": hid, "stacks": [0] * n_seats})

    def _kit_replay(self, events, board):
        streets = ("preflop", "flop", "turn", "river")
        for ev in events:
            if not isinstance(ev, dict):
                continue
            st = ev.get("street", self._hist_street)
            if st != self._hist_street and st in streets:
                k = {"flop": 3, "turn": 4, "river": 5}.get(st, 0)
                self._feed({"type": "board", "hand_id": self._hist_hand, "street": st, "board": list(board[:k])})
                self._hist_street = st
            a = ev.get("action")
            if a in ("small_blind", "big_blind"):
                self._feed({"type": "action", "hand_id": self._hist_hand, "seat": ev.get("seat"), "street": "preflop",
                            "action": "post", "amount": ev.get("amount", 0)})
                continue
            self._hist_k += 1
            self._feed({"type": "action", "hand_id": self._hist_hand, "seat": ev.get("seat"), "street": st,
                        "action": a, "amount": ev.get("amount", 0)})

    def _ingest_history(self, state):
        """Replay new events from state history (kit format) into the trackers."""
        if getattr(self, "_observe_seen", False):
            return
        hist = S(state, "history") or []
        hid = state.get("hand_number", state.get("hand_id"))
        if hid != getattr(self, "_hist_hand", object()):
            self._kit_new_hand(hid, len(state.get("folded") or S(state, "stacks") or []))
        self._kit_replay(hist[self._hist_n:], state.get("board") or [])
        self._hist_n = len(hist)

    def on_hand_end(self, summary):
        try:
            if getattr(self, "_observe_seen", False) or not isinstance(summary, dict):
                return
            hid = summary.get("hand_number")
            stacks = summary.get("stacks") or []
            if hid != getattr(self, "_hist_hand", object()):
                self._kit_new_hand(hid, len(stacks))
            hist = [h for h in (summary.get("history") or []) if h.get("action") not in ("small_blind", "big_blind")]
            self._kit_replay(hist[self._hist_k:], summary.get("board") or [])
            shown = summary.get("shown") or {}
            if shown:
                self._feed({"type": "showdown", "hand_id": hid,
                            "hands": {int(s): list(c) for s, c in shown.items() if c},
                            "winners": {int(w.get("seat")): w.get("amount", 0) for w in (summary.get("winners") or [])}})
            start = int(self.info.get("starting_stack", 0) or 0)
            self._feed({"type": "hand_end", "hand_id": hid,
                        "deltas": [int(x) - start for x in stacks] if start else []})
            self._hist_hand = ("ended", hid)
        except Exception:
            pass

    def act(self, state):
        try:
            self._ingest_history(state)
        except Exception:
            pass
        try:
            return sanitize(self._act(state), state)
        except Exception:
            return safe_default(state)

    def _act(self, state):
        started = time.perf_counter()
        hole = [_card(c) for c in S(state, "hole_cards")]
        board = [_card(c) for c in state.get("board", [])]
        opps = _remaining_opponents(state)
        ctx = {"hole": hole, "board": board, "opponents": opps, "started": started}
        stacks = S(state, "stacks")
        to_call = S(state, "to_call", 0) or 0
        me = state.get("seat", self.seat)
        my_stack = stacks[me] if stacks else None
        facing_allin = my_stack is not None and to_call > 0 and to_call >= 0.5 * my_stack
        if facing_allin:
            act = hook_facing_allin(self, state, ctx)
            if act is not None:
                return act
        street = S(state, "street") or ("preflop" if not board else "postflop")
        if street == "preflop":
            act = hook_preflop(self, state, ctx)
        elif to_call == 0:
            act = hook_betting(self, state, ctx)
        else:
            act = hook_facing_bet(self, state, ctx)
        if act is not None:
            return act
        win_rate, self.last_samples = _estimate_win_rate(hole, board, opps, self.rng,
                                                         deadline=started + THINK_SECONDS)
        ctx["win_rate"] = win_rate
        act = incumbent_policy(win_rate, state)
        if act.get("action") == "raise":
            intent = "value" if win_rate > 0.85 else "thin_value"
            amt = hook_sizing(self, state, ctx, intent)
            if amt is not None:
                act = {"action": "raise", "amount": int(amt)}
        return act
