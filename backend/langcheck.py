"""Checkers for quiz questions whose answer is a word or short text: Spanish present-tense
conjugations, English irregular verbs and plurals (and equation balancing, registered from
sciencecheck.py).

These only check words listed in the tables below. A verb or noun that isn't listed is
left unchecked rather than guessed, because a guess could "fix" a key that was right.
"""
import re
import unicodedata

from mathcheck import MathError, _claimed_index

BUILDERS = {}  # op -> function(task) -> TextTask


class TextTask:
    def __init__(self, question, accepted, display, checked_by, normalize=None):
        self.question = question
        self.normalize = normalize or norm
        self.accepted = {self.normalize(a) for a in accepted}
        self.display = display  # the answer as shown if it has to be put into the options
        self.checked_by = checked_by


def op(name):
    def register(fn):
        BUILDERS[name] = fn
        return fn
    return register


def norm(text):
    """Lowercase, NFC, no surrounding punctuation. Accents are kept: 'esta' is not 'está'."""
    text = unicodedata.normalize("NFC", str(text)).strip().lower()
    text = re.sub(r"^[\s\"'“”‘’¿¡*_]+|[\s\"'“”‘’?!.,;:*_]+$", "", text)
    return re.sub(r"\s+", " ", text)


def check_text_task(q):
    """Verify a text-answer question. Same result shape as mathcheck.check_question."""
    task = BUILDERS[str(q.get("op")).strip().lower()](q)
    raw = [str(o).strip() for o in q.get("options") or []]
    if len(raw) != 4 or not all(raw):
        raise MathError("need exactly 4 options")
    normed = [task.normalize(o) for o in raw]
    if len(set(normed)) != 4:
        raise MathError("two options are the same")
    claimed = _claimed_index(q.get("answer"))
    right = [i for i, n in enumerate(normed) if n in task.accepted]
    if len(right) > 1:
        raise MathError("more than one option is correct")
    shown = list(raw)
    if right:
        answer = right[0]
    else:
        answer = claimed if claimed is not None else 0
        shown[answer] = task.display
    corrected = answer != claimed or not right
    explanation = str(q.get("explanation") or "").strip()
    if corrected or not explanation:
        explanation = f"Mother Hen double-checked this: the correct answer is {task.display}."
    return {
        "question": task.question,
        "options": shown,
        "answer": answer,
        "explanation": explanation,
        "verified": True,
        "corrected": corrected,
        "model_said": raw[claimed] if (corrected and claimed is not None) else None,
        "checked_by": task.checked_by,
    }


# ---------- Spanish: present-tense conjugation ----------

PERSONS = ["yo", "tú", "él / ella / usted", "nosotros", "vosotros", "ellos / ellas / ustedes"]
PERSON_NAMES = {
    "yo": 0, "tu": 1, "tú": 1, "el": 2, "él": 2, "ella": 2, "usted": 2, "ud": 2, "ud.": 2,
    "nosotros": 3, "nosotras": 3, "vosotros": 4, "vosotras": 4, "ellos": 5, "ellas": 5,
    "ustedes": 5, "uds": 5, "uds.": 5,
}
ENDINGS = {
    "ar": ["o", "as", "a", "amos", "áis", "an"],
    "er": ["o", "es", "e", "emos", "éis", "en"],
    "ir": ["o", "es", "e", "imos", "ís", "en"],
}
REGULAR = set("""
hablar trabajar estudiar caminar cantar bailar comprar cocinar escuchar mirar llegar llamar
necesitar tomar usar viajar nadar ayudar buscar enseñar esperar ganar gastar lavar limpiar
llevar pagar preguntar preparar regresar sacar terminar tocar visitar desear entrar dejar
olvidar contestar descansar dibujar practicar manejar pasar cambiar cortar cuidar firmar
comer beber aprender leer correr vender comprender creer deber responder romper meter
esconder prometer sorprender
vivir escribir abrir recibir decidir subir compartir asistir describir discutir cubrir
existir permitir sufrir partir insistir
""".split())
# Stem-changing verbs: the last e/o/u of the stem changes when stressed (yo, tú, él, ellos).
STEM_CHANGE = {
    "ie": "pensar querer empezar entender preferir cerrar comenzar perder sentir mentir "
          "despertar sentar encender defender".split(),
    "ue": "poder dormir volver encontrar contar almorzar costar morir mostrar recordar soñar "
          "volar mover".split(),
    "i": "pedir servir repetir vestir medir".split(),
}
JUGAR = "jugar"  # u -> ue
YO_ONLY = {"hacer": "hago", "poner": "pongo", "salir": "salgo", "traer": "traigo",
           "caer": "caigo", "saber": "sé", "ver": "veo", "valer": "valgo"}
ZCO = "conocer parecer ofrecer conducir traducir producir".split()  # yo -zco
UIR = "construir incluir destruir huir contribuir".split()  # insert y
IRREGULAR = {
    "ser": ["soy", "eres", "es", "somos", "sois", "son"],
    "estar": ["estoy", "estás", "está", "estamos", "estáis", "están"],
    "ir": ["voy", "vas", "va", "vamos", "vais", "van"],
    "dar": ["doy", "das", "da", "damos", "dais", "dan"],
    "tener": ["tengo", "tienes", "tiene", "tenemos", "tenéis", "tienen"],
    "venir": ["vengo", "vienes", "viene", "venimos", "venís", "vienen"],
    "decir": ["digo", "dices", "dice", "decimos", "decís", "dicen"],
    "oír": ["oigo", "oyes", "oye", "oímos", "oís", "oyen"],
    "haber": ["he", "has", "ha", "hemos", "habéis", "han"],
    "oler": ["huelo", "hueles", "huele", "olemos", "oléis", "huelen"],
    "seguir": ["sigo", "sigues", "sigue", "seguimos", "seguís", "siguen"],
    "elegir": ["elijo", "eliges", "elige", "elegimos", "elegís", "eligen"],
    "ver": ["veo", "ves", "ve", "vemos", "veis", "ven"],
}
STRESSED = {0, 1, 2, 5}


def _change_stem(stem, new):
    vowel = {"ie": "e", "ue": "o", "i": "e"}[new]
    at = stem.rfind(vowel)
    return stem[:at] + new + stem[at + 1:]


def conjugate(verb):
    """All six present-tense forms of a verb we know, or raise MathError."""
    verb = norm(verb)
    if verb in IRREGULAR:
        return list(IRREGULAR[verb])
    stem, kind = verb[:-2], verb[-2:]
    if kind not in ENDINGS:
        raise MathError(f"not a Spanish infinitive: {verb!r}")
    forms = [stem + e for e in ENDINGS[kind]]
    if verb in REGULAR:
        return forms
    for new, verbs in STEM_CHANGE.items():
        if verb in verbs:
            changed = _change_stem(stem, new)
            return [changed + e if i in STRESSED else stem + e for i, e in enumerate(ENDINGS[kind])]
    if verb == JUGAR:
        return [("jueg" if i in STRESSED else "jug") + e for i, e in enumerate(ENDINGS["ar"])]
    if verb in YO_ONLY:
        forms[0] = YO_ONLY[verb]
        return forms
    if verb in ZCO:
        forms[0] = stem[:-1] + "zco"
        return forms
    if verb in UIR:
        return [stem + ("y" + e if i in STRESSED else e) for i, e in enumerate(ENDINGS["ir"])]
    raise MathError(f"verb not in the checker's list: {verb!r}")


def known_spanish_verbs():
    return sorted(REGULAR | set(IRREGULAR) | {v for vs in STEM_CHANGE.values() for v in vs}
                  | {JUGAR} | set(YO_ONLY) | set(ZCO) | set(UIR))


def _strip_pronoun(text):
    """'nosotros tenemos' -> 'tenemos' (options sometimes include the pronoun)."""
    words = norm(text).split(" ")
    while len(words) > 1 and (words[0] in PERSON_NAMES or words[0] in ("/",)):
        words = words[1:]
    return " ".join(words)


@op("conjugate")
def _conjugate(task):
    tense = norm(task.get("tense") or "present")
    if tense not in ("present", "presente", "present tense", "present indicative"):
        raise MathError("only the present tense is checked")
    person = PERSON_NAMES.get(norm(task.get("person") or ""))
    if person is None:
        raise MathError(f"unknown person {task.get('person')!r}")
    verb = norm(task.get("verb"))
    form = conjugate(verb)[person]
    return TextTask(f"Conjugate *{verb}* in the present tense for *{PERSONS[person]}*.",
                    accepted={form}, display=form, checked_by="spanish", normalize=_strip_pronoun)


# ---------- English: irregular verbs and plurals ----------

# base: (past forms, past participle forms). Both British and American forms are accepted.
IRREGULAR_VERBS = {
    "be": ("was were", "been"), "become": ("became", "become"), "begin": ("began", "begun"),
    "bite": ("bit", "bitten"), "blow": ("blew", "blown"), "break": ("broke", "broken"),
    "bring": ("brought", "brought"), "build": ("built", "built"), "buy": ("bought", "bought"),
    "catch": ("caught", "caught"), "choose": ("chose", "chosen"), "come": ("came", "come"),
    "cost": ("cost", "cost"), "cut": ("cut", "cut"), "do": ("did", "done"),
    "draw": ("drew", "drawn"), "drink": ("drank", "drunk"), "drive": ("drove", "driven"),
    "eat": ("ate", "eaten"), "fall": ("fell", "fallen"), "feel": ("felt", "felt"),
    "fight": ("fought", "fought"), "find": ("found", "found"), "fly": ("flew", "flown"),
    "forget": ("forgot", "forgotten"), "forgive": ("forgave", "forgiven"),
    "freeze": ("froze", "frozen"), "get": ("got", "got gotten"), "give": ("gave", "given"),
    "go": ("went", "gone"), "grow": ("grew", "grown"), "have": ("had", "had"),
    "hear": ("heard", "heard"), "hide": ("hid", "hidden"), "hit": ("hit", "hit"),
    "hold": ("held", "held"), "hurt": ("hurt", "hurt"), "keep": ("kept", "kept"),
    "know": ("knew", "known"), "lay": ("laid", "laid"), "lead": ("led", "led"),
    "leave": ("left", "left"), "lend": ("lent", "lent"), "let": ("let", "let"),
    "lose": ("lost", "lost"), "make": ("made", "made"), "mean": ("meant", "meant"),
    "meet": ("met", "met"), "pay": ("paid", "paid"), "put": ("put", "put"),
    "read": ("read", "read"), "ride": ("rode", "ridden"), "ring": ("rang", "rung"),
    "rise": ("rose", "risen"), "run": ("ran", "run"), "say": ("said", "said"),
    "see": ("saw", "seen"), "sell": ("sold", "sold"), "send": ("sent", "sent"),
    "set": ("set", "set"), "shake": ("shook", "shaken"), "shoot": ("shot", "shot"),
    "shut": ("shut", "shut"), "sing": ("sang", "sung"), "sink": ("sank", "sunk"),
    "sit": ("sat", "sat"), "sleep": ("slept", "slept"), "speak": ("spoke", "spoken"),
    "spend": ("spent", "spent"), "stand": ("stood", "stood"), "steal": ("stole", "stolen"),
    "stick": ("stuck", "stuck"), "sting": ("stung", "stung"), "strike": ("struck", "struck"),
    "swim": ("swam", "swum"), "swing": ("swung", "swung"), "take": ("took", "taken"),
    "teach": ("taught", "taught"), "tear": ("tore", "torn"), "tell": ("told", "told"),
    "think": ("thought", "thought"), "throw": ("threw", "thrown"),
    "understand": ("understood", "understood"), "wake": ("woke", "woken"),
    "wear": ("wore", "worn"), "win": ("won", "won"), "write": ("wrote", "written"),
    "dream": ("dreamed dreamt", "dreamed dreamt"), "learn": ("learned learnt", "learned learnt"),
    "burn": ("burned burnt", "burned burnt"), "spell": ("spelled spelt", "spelled spelt"),
}
IRREGULAR_PLURALS = {
    "child": "children", "man": "men", "woman": "women", "person": "people", "mouse": "mice",
    "goose": "geese", "tooth": "teeth", "foot": "feet", "ox": "oxen", "die": "dice",
    "cactus": "cacti cactuses", "fungus": "fungi funguses", "nucleus": "nuclei",
    "radius": "radii", "stimulus": "stimuli", "alumnus": "alumni", "analysis": "analyses",
    "crisis": "crises", "thesis": "theses", "hypothesis": "hypotheses", "basis": "bases",
    "diagnosis": "diagnoses", "phenomenon": "phenomena", "criterion": "criteria",
    "bacterium": "bacteria", "leaf": "leaves", "knife": "knives", "wife": "wives",
    "life": "lives", "half": "halves", "wolf": "wolves", "calf": "calves", "shelf": "shelves",
    "loaf": "loaves", "thief": "thieves", "elf": "elves", "sheep": "sheep", "deer": "deer",
    "fish": "fish fishes", "moose": "moose", "series": "series", "species": "species",
    "aircraft": "aircraft", "potato": "potatoes", "tomato": "tomatoes", "hero": "heroes",
    "echo": "echoes", "roof": "roofs", "chief": "chiefs", "belief": "beliefs", "chef": "chefs",
    "photo": "photos", "piano": "pianos", "index": "indices indexes",
    "appendix": "appendices appendixes", "matrix": "matrices matrixes",
    "vertex": "vertices vertexes",
}


@op("english_verb")
def _english_verb(task):
    verb = norm(task.get("verb"))
    if verb.startswith("to "):
        verb = verb[3:]
    form = norm(task.get("form") or "past").replace("-", " ").replace("_", " ")
    if verb not in IRREGULAR_VERBS:
        raise MathError(f"verb not in the checker's list: {verb!r}")
    past, participle = IRREGULAR_VERBS[verb]
    if form in ("past", "past tense", "simple past"):
        accepted, label = past.split(), "past tense"
    elif form in ("past participle", "participle"):
        accepted, label = participle.split(), "past participle"
    else:
        raise MathError("form must be past or past_participle")
    return TextTask(f"What is the {label} of “{verb}”?", accepted=accepted,
                    display=" / ".join(accepted), checked_by="english")


@op("plural")
def _plural(task):
    noun = norm(task.get("noun"))
    if noun not in IRREGULAR_PLURALS:
        raise MathError(f"noun not in the checker's list: {noun!r}")
    accepted = IRREGULAR_PLURALS[noun].split()
    return TextTask(f"What is the plural of “{noun}”?", accepted=accepted,
                    display=" / ".join(accepted), checked_by="english")
