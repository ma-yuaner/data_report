import { reviewKey, type HandbookBlock, type HandbookSection, type ReviewPolicy } from '@/api/riskFollowup'

export interface OutlineEntry { node: HandbookSection; siblings: HandbookSection[]; number: string; depth: number }

export function handbookOutline(nodes: HandbookSection[], prefix = '', depth = 1): OutlineEntry[] {
  return nodes.flatMap((node, index) => {
    const number = prefix + (index + 1)
    return [{ node, siblings: nodes, number, depth }, ...handbookOutline(node.children, number + '.', depth + 1)]
  })
}

export function section(title: string, blocks: HandbookBlock[] = []): HandbookSection {
  return { id: reviewKey().toLowerCase(), title, blocks, cases: [], examples: [], children: [] }
}

export function legacyHandbook(policy: ReviewPolicy) {
  const node: HandbookSection = { id: policy.id, title: policy.name, blocks: [], cases: [], examples: [], children: [] }
  const characters = Array.from(policy.basis)
  for (let offset = 0; offset < characters.length; offset += 4000) {
    const text = characters.slice(offset, offset + 4000).join('').trim()
    if (text) node.blocks.push({ kind: 'paragraph', text })
  }
  return { source: '历史登记正文', chapters: [node] }
}

export function importMarkdown(markdown: string): HandbookSection[] {
  const chapters: HandbookSection[] = []
  const stack: HandbookSection[] = []
  let paragraph: string[] = []
  function flush() {
    if (!paragraph.length) return
    if (!stack.length) throw new Error('请先用 # 写章标题，再填写正文。')
    const node = stack[stack.length - 1]
    const isList = paragraph.every(line => /^(?:[-*]|\d+[.)])\s+/.test(line))
    const isTable = paragraph.length > 1 && paragraph.every(line => line.includes('|')) && /^[\s|:-]+$/.test(paragraph[1])
    if (isList) node.blocks.push({ kind: 'list', text: paragraph.map(line => line.replace(/^(?:[-*]|\d+[.)])\s+/, '')).join('\n') })
    else if (isTable) node.blocks.push({ kind: 'table', text: paragraph.filter((_, index) => index !== 1).map(line => line.replace(/^\||\|$/g, '')).join('\n') })
    else node.blocks.push({ kind: 'paragraph', text: paragraph.join('\n') })
    paragraph = []
  }
  for (const input of markdown.split(/\r?\n/)) {
    const line = input.trim()
    const heading = /^(#{1,6})\s+(.+)$/.exec(line)
    if (heading) {
      flush()
      const depth = heading[1].length
      if (depth > 3 || depth > stack.length + 1) throw new Error('目录支持 # 章、## 节、### 条款，请逐级填写。')
      const node = section(heading[2])
      const siblings = depth === 1 ? chapters : stack[depth - 2].children
      siblings.push(node)
      stack.length = depth - 1
      stack.push(node)
    } else if (!line) flush()
    else paragraph.push(line)
  }
  flush()
  if (!chapters.length) throw new Error('未找到章节标题。')
  return chapters
}

function sample(id: string, title: string, blocks: HandbookBlock[], examples: HandbookSection['examples'] = [], children: HandbookSection[] = []): HandbookSection {
  return { id, title, blocks, cases: [], examples, children }
}

export const trainingHandbook: ReviewPolicy = {
  id: 'training-handbook', name: '风控业务手册', policyVersion: '培训整理稿',
  start: '', end: '', scope: '申诉、差异单、出票核查和售后培训', basis: '风控培训材料整理',
  handbook: {
    source: '《风控培训文档 11.10》整理。案例已脱敏改写，制度条款的有效性由业务确认。',
    chapters: [
      sample('appeals', '申诉与差异单', [{ kind: 'paragraph', text: '录入前先核对业务类型和处理路径。结案时记录结果和依据，便于后续核查。' }], [], [
        sample('difference', '差异单录入', [
          { kind: 'list', text: '核对差异事实，选择对应的差异原因与金额分类。\n在说明里写清发生了什么，以及为什么需要补退或调整。' },
          { kind: 'question', text: '能直接复制平台回复吗？\n建议提炼成一句话，让同事能从说明中判断差异原因。' },
        ], [
          { title: '退票作废后补退差价', detail: '背景：退票作废后的可盈利金额受限，需要补退差价。\n信息不足的写法：「平台已回复，请处理。」\n清晰的写法：「退票作废后的可盈利金额受限，需补退差价。」\n核查点：备注应解释发生原因和调整目的，实际收支还需按订单凭证核对。' },
        ]),
        sample('appeal-close', '申诉结果与结案', [
          { kind: 'table', text: '处理结果|培训材料中的后续动作\n申诉成功|进入差异单录入，核对是否已有记录\n申诉失败|在处理意见中说明平台驳回原因' },
        ], [
          { title: '平台驳回后如何写结案意见', detail: '情景：平台以缺少相关申诉凭证为由驳回。\n处理：选用对应结案原因，记录平台驳回理由及实际缺失的材料，便于后续复核。' },
        ]),
      ]),
      sample('threshold', '止损、对赌与报备', [{ kind: 'paragraph', text: '核查对赌订单时，说明政策投放逻辑及超阈值订单出现的原因。' }], [], [
        sample('reports', '报备材料与复核', [
          { kind: 'list', text: '培训材料要求留存文字报备与截图。\n复核时核对报备范围、有效期和适用的配置。' },
          { kind: 'note', text: '涉及临时阈值、历史豁免或范围冲突时，先核对当时适用版本和证据。' },
        ], [
          { title: '只有少量超阈值订单，怎么回填', detail: '情景一：政策进单量较多，多数订单可正常执行，少量操作失败后产生超阈值亏损。\n情景二：政策进单量本身较少，因而超阈值订单也少。\n回填时写清实际投放逻辑和形成原因，并附对应报备依据。' },
        ]),
      ]),
      sample('aftersales', '售后与专项操作', [], [], [
        sample('ndc-void', 'NDC 作废核查', [
          { kind: 'list', text: '作废时查看界面是否提示退款金额。\n作废后检查历史记录，保留核查依据。' },
        ], [
          { title: 'NDC 作废后的退款提示核查', detail: '情景：同事完成作废操作，需要确认退款相关提示。\n先回看作废时的提示，再查历史记录。若信息不完整，记录缺失证据并继续核实。' },
        ]),
      ]),
    ],
  },
}
