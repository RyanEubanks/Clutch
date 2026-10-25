// Symbol keyboards for typing answers: one per kind of subject, picked from what's being
// studied. Keys insert plain text both people and the tutor read easily, in the forms the
// backend's math checker understands (^ for powers, × ÷ − √ π). "▮" marks where the
// cursor lands, so √(▮) puts it inside the brackets.

const k = (label, insert = label, title = '') => ({ label, insert, title })

const OPERATORS = [
  k('+'), k('−', '−', 'minus'), k('×', '×', 'times'), k('÷', '÷', 'divided by'), k('='),
  k('('), k(')'),
]
const COMPARE = [k('≠'), k('<'), k('>'), k('≤'), k('≥'), k('≈', '≈', 'about equal')]
const POWERS = [
  k('x²', '^2', 'squared'), k('x³', '^3', 'cubed'), k('xⁿ', '^(▮)', 'to the power'),
  k('√', '√(▮)', 'square root'), k('a⁄b', '(▮)/()', 'fraction'),
]

export const KEYBOARDS = {
  basic: {
    name: 'Basic math',
    keys: [...OPERATORS, ...COMPARE.slice(0, 3), k('a⁄b', '(▮)/()', 'fraction'), k('%'), k('.'),
      k('x²', '^2', 'squared'), k('√', '√(▮)', 'square root'), k('π')],
  },
  algebra: {
    name: 'Algebra',
    keys: [...OPERATORS, ...COMPARE, ...POWERS, k('±'), k('|x|', '|▮|', 'absolute value'),
      k('π'), k('x'), k('y'), k('f(x)', 'f(▮)'), k('log', 'log(▮)'), k('ln', 'ln(▮)')],
  },
  calculus: {
    name: 'Calculus',
    keys: [...POWERS, k('d/dx', 'd/dx (▮)', 'derivative'), k('′', '′', 'prime: f′(x)'),
      k('∫', '∫ ▮ dx', 'integral'), k('∫ₐᵇ', '∫ from ▮ to  of  dx', 'definite integral'),
      k('lim', 'lim x→▮ ', 'limit'), k('→'), k('∞'), k('Σ'), k('Δ'), k('∂'),
      k('eˣ', 'e^(▮)'), k('ln', 'ln(▮)'), k('sin', 'sin(▮)'), k('cos', 'cos(▮)'), k('tan', 'tan(▮)'),
      k('π'), k('θ'), k('×'), k('÷'), k('±'), k('≤'), k('≥')],
  },
  linalg: {
    name: 'Linear algebra',
    keys: [k('[ ]', '[[▮, ], [, ]]', '2×2 matrix'), k('[ 3×3 ]', '[[▮, , ], [, , ], [, , ]]', '3×3 matrix'),
      k('⟨ ⟩', '⟨▮, ⟩', 'vector'), k('λ'), k('det', 'det(▮)'), k('Aᵀ', 'ᵀ', 'transpose'),
      k('A⁻¹', '^(-1)', 'inverse'), k('·', '·', 'dot product'), k('×', '×', 'cross product'),
      k('‖v‖', '‖▮‖', 'length'), k('I'), k('0'), k('≠'), k('−'), k('x²', '^2'), k('√', '√(▮)')],
  },
  geometry: {
    name: 'Geometry',
    keys: [k('°'), k('π'), k('∠'), k('△'), k('⊥'), k('∥'), k('≅'), k('∼'), k('θ'),
      k('x²', '^2'), k('x³', '^3'), k('√', '√(▮)'), k('a⁄b', '(▮)/()'), k('×'), k('÷'), k('−'), k('='),
      k('sin', 'sin(▮)'), k('cos', 'cos(▮)'), k('tan', 'tan(▮)')],
  },
  stats: {
    name: 'Statistics',
    keys: [k('μ'), k('σ'), k('σ²', 'σ^2'), k('x̄'), k('Σ'), k('P( )', 'P(▮)', 'probability'),
      k('P(A|B)', 'P(▮ | )', 'conditional probability'), k('!', '!', 'factorial'),
      k('nCr', 'C(▮, )', 'combinations'), k('≈'), k('±'), k('≤'), k('≥'), k('%'),
      k('a⁄b', '(▮)/()'), k('√', '√(▮)'), k('x²', '^2'), k('×'), k('÷'), k('−')],
  },
  physics: {
    name: 'Physics',
    keys: [k('Δ'), k('θ'), k('ω'), k('λ'), k('μ'), k('ρ'), k('Ω'), k('·'), k('×'), k('÷'),
      k('x²', '^2'), k('√', '√(▮)'), k('×10ⁿ', '×10^(▮)', 'scientific notation'), k('→'),
      k('°'), k('m/s'), k('m/s²', 'm/s^2'), k('N'), k('J'), k('W'), k('kg')],
  },
  chemistry: {
    name: 'Chemistry',
    keys: [...'₀₁₂₃₄₅₆₇₈₉'.split('').map((d) => k(d, d, 'subscript')),
      k('→', '→', 'yields'), k('⇌', '⇌', 'equilibrium'), k('⁺', '⁺', 'positive charge'),
      k('⁻', '⁻', 'negative charge'), k('²⁺'), k('²⁻'), k('Δ'), k('°C'), k('·'),
      k('(aq)'), k('(s)'), k('(l)'), k('(g)'), k('↑'), k('↓')],
  },
  spanish: {
    name: 'Spanish',
    keys: ['á', 'é', 'í', 'ó', 'ú', 'ñ', 'ü', '¿', '¡', 'Á', 'É', 'Í', 'Ó', 'Ú', 'Ñ'].map((c) => k(c)),
  },
  french: {
    name: 'French',
    keys: ['é', 'è', 'ê', 'ë', 'à', 'â', 'ç', 'î', 'ï', 'ô', 'û', 'ù', 'ü', 'œ', '«', '»', 'É', 'À', 'Ç']
      .map((c) => k(c)),
  },
  german: {
    name: 'German',
    keys: ['ä', 'ö', 'ü', 'ß', 'Ä', 'Ö', 'Ü', '„', '“'].map((c) => k(c)),
  },
}

// Checked in order, so specific subjects win over general ones ("Linear Algebra" isn't
// plain algebra, "Precalculus" still gets calculus symbols).
const DETECT = [
  ['linalg', /linear algebra|matri(x|ces)|eigen|vector|determinant/i],
  ['calculus', /calc|derivativ|integra|limit|differential|chain rule|antideriv/i],
  ['stats', /statistic|probabilit|distribution|standard deviation|\bmean of|median|variance/i],
  ['physics', /physic|newton|velocity|accelerat|momentum|kinematic|force|energy|circuit/i],
  ['chemistry', /chem|stoichiometr|molecul|periodic table|reaction|acid|base|atom/i],
  ['geometry', /geometr|triangle|angle|circle|pythag|polygon|area|perimeter|volume/i],
  ['spanish', /spanish|español|espanol|conjugat/i],
  ['french', /french|français|francais/i],
  ['german', /german|deutsch/i],
  ['algebra', /algebra|equation|polynomial|quadratic|factor|function|linear|exponent|logarithm|inequalit|slope/i],
  ['basic', /math|arithmetic|addition|subtraction|multiplication|division|fraction|times table|decimal|percent/i],
]

/** The keyboard that fits what's being studied, from the topic label first, then the chat. */
export function pickKeyboard(topicLabel, chatText = '') {
  for (const text of [topicLabel, chatText]) {
    if (!text) continue
    for (const [id, pattern] of DETECT) if (pattern.test(text)) return id
  }
  return 'algebra' // a sensible general-purpose math keyboard
}

/** Insert a key's text into `value` over the selection; returns the new value and caret. */
export function insertKey(value, start, end, insert) {
  const marker = insert.indexOf('▮')
  const text = insert.replace('▮', '')
  const next = value.slice(0, start) + text + value.slice(end)
  const caret = start + (marker >= 0 ? marker : text.length)
  return { value: next, caret }
}
