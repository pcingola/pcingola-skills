import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'
import type { Engine, Plugin } from 'claude-code/testing'

const URL = 'http://127.0.0.1:8765'
const UNCUT = { isStdoutTruncated: false, isStderrTruncated: false }
// /studio as the person types it at the terminal.
const STUDIO = {
  command: 'studio',
  args: '',
  origin: { kind: 'composer' },
  presentation: { isFullscreen: false, columns: 120 },
} as Parameters<Engine['command']['run']>[0]

type Sent = { path: string; body: Record<string, unknown> }
type ToolArgs = Parameters<Engine['tool']['call']>[0]
type TurnEnd = Parameters<Engine['turn']['complete']>[0]

// What the mocked world beneath the mod recorded, the server's stdout the test writes to, and
// the switches that change how the world answers.
type World = {
  sent: Sent[]
  prompts: string[]
  opened: string[][]
  spawned: string[][]
  toasts: string[]
  registered: string[]
  chunk: (text: string) => void
  write: (line: string) => void
  exit: () => void
  clock: ReturnType<typeof mock.clock>
  fetch: 'ok' | 'not-ok' | 'fail' | 'hang'
  drop: boolean
  // Calls of this tool wait at the bottom until the test releases them, in order.
  holdTool?: string
  held: (() => void)[]
}

type WorldOptions = { env?: Record<string, string>; uname?: string }

// Mocks everything the mod reaches beneath it: a server whose stdout the test writes, the
// HTTP endpoints, prompt submission, the browser opener and the session's own nouns.
function world(on: On, options: WorldOptions = {}): World {
  const pieces: (string | null)[] = []
  let wake: (() => void) | undefined
  const push = (text: string | null): void => {
    pieces.push(text)
    wake?.()
  }
  const w: World = {
    sent: [],
    prompts: [],
    opened: [],
    spawned: [],
    toasts: [],
    registered: [],
    chunk: text => push(text),
    write: line => push(`${line}\n`),
    exit: () => push(null),
    clock: mock.clock(on),
    fetch: 'ok',
    drop: false,
    held: [],
  }
  mock.env(on, options.env ?? {})
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('tool.register', (_, e) => {
    w.registered.push(e.name)
    return { value: { tool: `mcp__studio__${e.name}` } }
  })
  on('ui.status', () => ({ value: undefined }))
  on('ui.log', () => ({ value: undefined }))
  on('ui.toast', (_, e) => {
    w.toasts.push(e.text)
    return { value: undefined }
  })
  on('process.run', (_, e) => {
    if (e.argv[0] === 'uname') return { value: { exitCode: 0, stdout: `${options.uname ?? 'Darwin'}\n`, stderr: '', ...UNCUT } }
    w.opened.push([...e.argv])
    return { value: { exitCode: 0, stdout: '', stderr: '', ...UNCUT } }
  })
  on('process.spawn', async function* (_, e) {
    w.spawned.push([...e.argv])
    for (;;) {
      if (pieces.length === 0) {
        await new Promise<void>(resolve => (wake = resolve))
        continue
      }
      const piece = pieces.shift()
      if (piece === null || piece === undefined) return { value: { code: 0, signal: null } }
      yield { stream: 'stdout' as const, text: piece }
    }
  })
  on('http.fetch', (_, e) => {
    if (w.fetch === 'fail') return { deny: 'connection refused' }
    if (w.fetch === 'hang') return new Promise<never>(() => undefined)
    w.sent.push({ path: e.url.slice(URL.length), body: JSON.parse(e.init?.body ?? '{}') })
    const ok = w.fetch === 'ok'
    return { value: { status: ok ? 200 : 500, ok, headers: {}, text: '' } }
  })
  on('prompt.submit', (_, e) => {
    w.prompts.push(e.text)
    return w.drop ? { drop: 'blocked' } : { text: e.text }
  })
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', () => ({ text: '' }))
  on('tool.call', async (_, e) => {
    if (e.tool === w.holdTool) await new Promise<void>(resolve => w.held.push(resolve))
    return { result: 'ran' }
  })

  return w
}

const events = (w: World, kind: string) =>
  w.sent.filter(s => s.path === '/event' && s.body.kind === kind).map(s => s.body)

const states = (w: World) => events(w, 'state').map(({ busy, current, queued }) => ({ busy, current, queued }))

// Stands for the person: above the mod, it allows every approval no hook beneath settled, as a
// person pressing "Yes" in the dialog would (the kit itself refuses such an ask at once).
const PERSON: Plugin = {
  name: 'person',
  tier: 'prepend',
  register: on => {
    on('classic.PermissionRequest', async (_, e, next) => {
      const result = await next(e)
      return result.decision === undefined ? { ...result, decision: { behavior: 'allow' } } : result
    })
  },
}

const heartbeats = (w: World) => w.sent.filter(s => s.path === '/heartbeat').length

async function startStudio($: Engine, w: World): Promise<string | undefined> {
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const run = $.command.run(STUDIO)
  w.write(JSON.stringify({ type: 'ready', url: URL }))
  const result = await run
  await w.clock.settle()

  return result.text
}

const request = (id: string, extra: Record<string, unknown> = {}) => ({
  id,
  action: 'generate',
  kind: 'image',
  skill: 'images',
  project: '/studio/images/cats',
  brief: 'a cat',
  ...extra,
})

async function sendRequest(w: World, id: string): Promise<void> {
  w.write(JSON.stringify({ type: 'request', request: request(id) }))
  await w.clock.settle()
}

const end = (turnId: string, agentId?: string): TurnEnd =>
  ({ reason: 'answer', answer: '', durationMs: 1, isAborted: false, turnId, agentId }) as TurnEnd

// Starts the main loop's turn with `text` as its prompt.
async function begin($: Engine, w: World, turnId: string, text: string): Promise<void> {
  await $.turn.start({ text, turnId })
  await w.clock.settle()
}

async function finish($: Engine, w: World, turnId: string): Promise<void> {
  await $.turn.complete(end(turnId))
  await w.clock.settle()
}

test('/studio starts the server, opens the page, publishes state and heartbeats every 5 s', async ($, on) => {
  const w = world(on)
  expect(await startStudio($, w)).toBe(`Studio is running at ${URL}`)
  expect(w.spawned).toHaveLength(1)
  expect(w.spawned[0]?.[0]).toMatch(/\/server\/studio-server\.sh$/)
  expect(w.opened).toEqual([['open', URL]])
  expect(states(w)).toEqual([{ busy: false, current: null, queued: [] }])

  await w.clock.advance(10_000)
  expect(heartbeats(w)).toBe(2)

  // A second /studio reuses the server and opens the page again.
  expect((await $.command.run(STUDIO)).text).toBe(`Studio is running at ${URL}`)
  await w.clock.settle()
  expect(w.spawned).toHaveLength(1)
  expect(w.opened).toHaveLength(2)
})

test('the page opens with cmd start on Windows', async ($, on) => {
  const w = world(on, { env: { OS: 'Windows_NT' } })
  await startStudio($, w)
  expect(w.opened).toEqual([['cmd', '/c', 'start', '', URL]])
})

test('the page opens with xdg-open on Linux', async ($, on) => {
  const w = world(on, { uname: 'Linux' })
  await startStudio($, w)
  expect(w.opened).toEqual([['xdg-open', URL]])
})

test('after the server exits: no heartbeats, the tools are refused, /studio spawns a new one', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  w.exit()
  await w.clock.settle()
  expect(w.toasts).toHaveLength(1)
  const beats = heartbeats(w)
  await w.clock.advance(20_000)
  expect(heartbeats(w)).toBe(beats)
  const result = await $.tool.call({ tool: 'mcp__studio__post', text: 'late' } as ToolArgs)
  expect(JSON.stringify(result)).toContain('not running')

  const run = $.command.run(STUDIO)
  w.write(JSON.stringify({ type: 'ready', url: URL }))
  expect((await run).text).toBe(`Studio is running at ${URL}`)
  expect(w.spawned).toHaveLength(2)
})

test('a server that exits before ready: /studio says it could not start', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const run = $.command.run(STUDIO)
  w.exit()
  expect((await run).text).toMatch(/^Studio could not start/)
  expect(w.toasts).toEqual([])
})

test('a server not ready in 5 s: /studio says it is starting, then opens the page or toasts a failure', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const run = $.command.run(STUDIO)
  await w.clock.settle()
  const waited = w.clock.advance(5000)
  expect((await run).text).toMatch(/^Studio is starting/)
  await waited
  expect(w.opened).toEqual([])
  w.write(JSON.stringify({ type: 'ready', url: URL }))
  await w.clock.settle()
  expect(w.opened).toEqual([['open', URL]])

  // A second start that fails after the "starting" answer is told with a toast.
  w.exit()
  await w.clock.settle()
  w.toasts.length = 0
  const again = $.command.run(STUDIO)
  await w.clock.settle()
  const waitedAgain = w.clock.advance(5000)
  expect((await again).text).toMatch(/^Studio is starting/)
  await waitedAgain
  w.exit()
  await w.clock.settle()
  expect(w.toasts).toHaveLength(1)
  expect(w.toasts[0]).toMatch(/^Studio could not start/)
})

test('a request becomes a prompt naming the workspace skill with the JSON verbatim', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  const req = request('r1', { refs: ['/a b/ref.png'], note: 'quote " and ```' })
  w.write(JSON.stringify({ type: 'request', request: req }))
  await w.clock.settle()

  expect(w.prompts).toHaveLength(1)
  const prompt = w.prompts[0] ?? ''
  expect(prompt).toContain('`studio:images`')
  expect(prompt).toContain('Skill tool')
  expect(prompt).toContain('mcp__studio__post')
  expect(prompt).toContain('mcp__studio__note')
  const block = /```json\n([\s\S]*)\n```\n/.exec(prompt)?.[1] ?? ''
  expect(JSON.parse(block)).toEqual(req)
})

test('a request of another kind names the workspace skill it carries', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  const req = request('r1', { kind: 'infographic', project: '/studio/infographics/heat-pump' })
  w.write(JSON.stringify({ type: 'request', request: req }))
  await w.clock.settle()

  expect(w.prompts).toHaveLength(1)
  expect(w.prompts[0]).toContain('`studio:images`')
  const block = /```json\n([\s\S]*)\n```\n/.exec(w.prompts[0] ?? '')?.[1] ?? ''
  expect(JSON.parse(block)).toEqual(req)
})

test('a slide request names studio:images and carries its slide and fields verbatim', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  const change = request('r1', { kind: 'slide', project: '/studio/slides/garden', action: 'change', slide: 2,
    version: 3, marks: [], note: 'shorter title', marked: null, mask: null })
  const assemble = request('r2', { kind: 'slide', project: '/studio/slides/garden', action: 'assemble',
    assembly: 'native', versions: { 1: 2, 2: 3 } })
  w.write(JSON.stringify({ type: 'request', request: change }))
  w.write(JSON.stringify({ type: 'request', request: assemble }))
  await w.clock.settle()

  expect(w.prompts).toHaveLength(2)
  for (const [i, req] of [change, assemble].entries()) {
    expect(w.prompts[i]).toContain('`studio:images`')
    const block = /```json\n([\s\S]*)\n```\n/.exec(w.prompts[i] ?? '')?.[1] ?? ''
    expect(JSON.parse(block)).toEqual(req)
  }
})

test('stdout lines split across pieces and several in one piece are all read', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  const one = JSON.stringify({ type: 'request', request: request('r1') })
  const two = JSON.stringify({ type: 'request', request: request('r2') })
  const three = JSON.stringify({ type: 'request', request: request('r3') })
  w.chunk(one.slice(0, 10))
  w.chunk(`${one.slice(10)}\n${two}\n${three.slice(0, 5)}`)
  w.chunk(`${three.slice(5)}\n`)
  await w.clock.settle()
  expect(w.prompts.map(p => /"id": "(r\d)"/.exec(p)?.[1])).toEqual(['r1', 'r2', 'r3'])
})

test('a bad stdout line is skipped and the next one still works', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  w.write('this is not json')
  w.write(JSON.stringify({ type: 'request', request: { id: 'x', skill: '../evil' } }))
  await sendRequest(w, 'r2')
  expect(w.prompts).toHaveLength(1)
  expect(w.prompts[0]).toContain('"id": "r2"')
})

test('state: current while idle, queued while busy, turns credited by their prompt', async ($, on) => {
  const w = world(on)
  await startStudio($, w)

  await sendRequest(w, 'r1')
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r1', queued: [] })
  const [p1] = w.prompts

  await begin($, w, 't1', p1 ?? '')
  expect(states(w).at(-1)).toEqual({ busy: true, current: 'r1', queued: [] })

  await sendRequest(w, 'r2')
  await sendRequest(w, 'r3')
  expect(states(w).at(-1)).toEqual({ busy: true, current: 'r1', queued: ['r2', 'r3'] })

  await finish($, w, 't1')
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r2', queued: ['r3'] })
  expect(events(w, 'turn').at(-1)).toEqual({ kind: 'turn', reason: 'answer' })

  // A turn the person started at the terminal runs no request.
  await begin($, w, 't2', 'what is in this folder?')
  expect(states(w).at(-1)).toEqual({ busy: true, current: null, queued: ['r2', 'r3'] })
  await finish($, w, 't2')
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r2', queued: ['r3'] })

  // A turn that runs r3's prompt, framed: r2, before it, is dropped.
  await begin($, w, 't3', `The studio plugin sent a message:\n${w.prompts[2] ?? ''}`)
  expect(states(w).at(-1)).toEqual({ busy: true, current: 'r3', queued: [] })
  await finish($, w, 't3')
  expect(states(w).at(-1)).toEqual({ busy: false, current: null, queued: [] })

  // A subagent's turn changes nothing.
  const count = states(w).length
  await $.turn.start({ text: '', turnId: 'a1', agentId: 'agent-1' })
  await $.turn.complete(end('a1', 'agent-1'))
  await w.clock.settle()
  expect(states(w)).toHaveLength(count)
})

test('a dropped submission leaves the queue', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  w.drop = true
  await sendRequest(w, 'r1')
  expect(states(w).at(-1)).toEqual({ busy: false, current: null, queued: [] })

  w.drop = false
  await sendRequest(w, 'r2')
  expect(states(w).at(-1)).toEqual({ busy: false, current: 'r2', queued: [] })
})

test('the tools are refused while the server is not running', async ($, on) => {
  const w = world(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  for (const call of [
    { tool: 'mcp__studio__post', text: 'hi' },
    { tool: 'mcp__studio__note', text: 'working' },
  ]) {
    const result = await $.tool.call(call as ToolArgs)
    expect(JSON.stringify(result)).toContain('not running')
  }
  expect(w.sent).toEqual([])
})

test('the tools post their events while the server runs', async ($, on) => {
  const w = world(on)
  await startStudio($, w)

  await $.tool.call({ tool: 'mcp__studio__post', text: 'done', images: ['/p/v1.png'] } as ToolArgs)
  await $.tool.call({ tool: 'mcp__studio__note', text: 'step 1' } as ToolArgs)
  expect(events(w, 'agent')).toEqual([{ kind: 'agent', text: 'done', images: ['/p/v1.png'] }])
  expect(events(w, 'note')).toEqual([{ kind: 'note', text: 'step 1' }])

  // The mod registers post and note alone.
  expect(w.registered).toEqual(['post', 'note'])
})

test('a fetch that fails or is not ok denies post and throws nothing', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  for (const mode of ['fail', 'not-ok'] as const) {
    w.fetch = mode
    const result = await $.tool.call({ tool: 'mcp__studio__post', text: 'x' } as ToolArgs)
    expect(JSON.stringify(result)).toContain('did not take')
    await sendRequest(w, `r-${mode}`)
    await w.clock.advance(5000)
  }
  expect(w.prompts).toHaveLength(2)
})

test('ask is sent when a person is asked, and ask-done once the call settled', async ($, on) => {
  const w = world(on)
  on('tool.check', () => ({ decision: 'ask' }))
  // Nothing beneath decides: the dialog would show.
  on('classic.PermissionRequest', () => ({}))
  await startStudio($, w)

  await $.tool.call({ tool: 'Bash', command: 'rm -rf build' })
  await w.clock.settle()
  expect(events(w, 'ask')).toEqual([{ kind: 'ask', tool: 'Bash', text: 'rm -rf build' }])
  expect(events(w, 'ask-done')).toHaveLength(1)
  const kinds = w.sent.filter(s => s.path === '/event').map(s => s.body.kind)
  expect(kinds.indexOf('ask')).toBeLessThan(kinds.indexOf('ask-done'))
})

test('no ask when a hook beneath settles the approval, or when the call is allowed', async ($, on) => {
  const w = world(on)
  let verdict: 'ask' | 'allow' = 'ask'
  on('tool.check', () => ({ decision: verdict }))
  on('classic.PermissionRequest', () => ({ decision: { behavior: 'allow' } }))
  await startStudio($, w)
  await $.tool.call({ tool: 'Bash', command: 'ls' })
  verdict = 'allow'
  await $.tool.call({ tool: 'Bash', command: 'pwd' })
  await w.clock.settle()
  expect(events(w, 'ask')).toEqual([])
  expect(events(w, 'ask-done')).toEqual([])
})

test('an ask still open when the turn ends gets ask-done then, and only once', { plugins: [PERSON] }, async ($, on) => {
  const w = world(on)
  w.holdTool = 'Write'
  on('tool.check', () => ({ decision: 'ask' }))
  on('classic.PermissionRequest', () => ({}))
  await startStudio($, w)

  const call = $.tool.call({ tool: 'Write', file_path: '/tmp/x', content: 'x' })
  await w.clock.settle()
  expect(events(w, 'ask')).toEqual([{ kind: 'ask', tool: 'Write', text: '/tmp/x' }])
  expect(w.held).toHaveLength(1)
  expect(events(w, 'ask-done')).toEqual([])
  await begin($, w, 't1', 'go')
  await finish($, w, 't1')
  expect(events(w, 'ask-done')).toHaveLength(1)
  w.held[0]?.()
  await call
  await w.clock.settle()
  expect(events(w, 'ask-done')).toHaveLength(1)
})

test('the session end sends ended to the page', async ($, on) => {
  const w = world(on)
  on('session.end', (_, e) => ({ sessionId: e.sessionId }))
  await startStudio($, w)
  await $.session.end({
    reason: 'prompt_input_exit',
    sessionId: 's1',
    resume: {},
  } as unknown as Parameters<Engine['session']['end']>[0])
  expect(events(w, 'ended')).toEqual([{ kind: 'ended' }])
})

test('a turn credited to a later request drops the earlier ones and every other it holds', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  await sendRequest(w, 'r1')
  await sendRequest(w, 'r2')
  await sendRequest(w, 'r3')
  await sendRequest(w, 'r4')
  const [p1, p2, p3, p4] = w.prompts
  // The turn runs r2 and also holds r4's text; r1, before it, is gone too.
  await begin($, w, 't1', `${p2}\n${p4}`)
  expect(states(w).at(-1)).toEqual({ busy: true, current: 'r2', queued: ['r3'] })
  expect(p1 && p3).toBeTruthy()
})

test('a POST that gets no answer marks the server down until a heartbeat is answered', async ($, on) => {
  const w = world(on)
  await startStudio($, w)
  w.fetch = 'hang'
  const first = $.tool.call({ tool: 'mcp__studio__post', text: 'a' } as ToolArgs)
  await w.clock.settle()
  const advanced = w.clock.advance(2000)
  expect(JSON.stringify(await first)).toContain('did not take')
  await advanced

  // Down: refused at once, without a fetch, however many earlier POSTs hang.
  const before = w.sent.length
  const second = await $.tool.call({ tool: 'mcp__studio__note', text: 'b' } as ToolArgs)
  expect(JSON.stringify(second)).toContain('did not take')
  expect(w.sent.length).toBe(before)

  // An answered heartbeat brings it back.
  w.fetch = 'ok'
  await w.clock.advance(5000)
  expect(w.sent.at(-1)).toEqual({ path: '/event', body: { kind: 'state', busy: false, current: null, queued: [] } })
  const third = await $.tool.call({ tool: 'mcp__studio__post', text: 'c' } as ToolArgs)
  expect(JSON.stringify(third)).toContain('Shown in the Studio page')
  expect(events(w, 'agent').map(e => e.text)).toEqual(['c'])
})

test('the server exiting after session.end is not told with a toast', async ($, on) => {
  const w = world(on)
  on('session.end', (_, e) => ({ sessionId: e.sessionId }))
  await startStudio($, w)
  await $.session.end({ reason: 'clear', sessionId: 's1', resume: {} } as unknown as Parameters<
    Engine['session']['end']
  >[0])
  w.exit()
  await w.clock.settle()
  expect(w.toasts).toEqual([])
})

test('two parallel calls with the same input: the one settled silently sends no ask-done', { plugins: [PERSON] }, async ($, on) => {
  const w = world(on)
  w.holdTool = 'Write'
  let requests = 0
  on('tool.check', () => ({ decision: 'ask' }))
  // The first PermissionRequest is settled by a hook beneath; the second shows the dialog.
  on('classic.PermissionRequest', () => (requests++ === 0 ? { decision: { behavior: 'allow' } } : {}))
  await startStudio($, w)

  const input = { tool: 'Write', file_path: '/tmp/same', content: 'x' } as const
  const a = $.tool.call(input)
  await w.clock.settle()
  const b = $.tool.call(input)
  await w.clock.settle()
  expect(events(w, 'ask')).toEqual([{ kind: 'ask', tool: 'Write', text: '/tmp/same' }])
  expect(w.held).toHaveLength(2)

  w.held[0]?.()
  await a
  await w.clock.settle()
  expect(events(w, 'ask-done')).toEqual([])
  w.held[1]?.()
  await b
  await w.clock.settle()
  expect(events(w, 'ask-done')).toHaveLength(1)
})
