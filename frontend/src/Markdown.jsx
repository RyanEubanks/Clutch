import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'

// The model sometimes writes \( ... \) and \[ ... \] instead of $ ... $ and $$ ... $$,
// so convert those before rendering. remark-math only treats $$ as display math when the
// $$ fences sit on their own lines, so a one-line $$ ... $$ is also moved onto its own lines
// (otherwise it renders small and inline, and long equations wrap mid-formula).
function normalizeMath(text) {
  return text
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, m) => `$$${m}$$`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, m) => `$${m}$`)
    .replace(/\$\$([\s\S]+?)\$\$/g, (_, m) => `\n\n$$\n${m.trim()}\n$$\n\n`)
}

export default function Markdown({ children }) {
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
        {normalizeMath(children || '')}
      </ReactMarkdown>
    </div>
  )
}
