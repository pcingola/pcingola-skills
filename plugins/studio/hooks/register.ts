import type { EngineInterface, Register } from 'claude-code'

// The Studio mod: starts the studio server, turns the page's requests into prompts, serves the
// tools the agent answers the page with, and reports busy, queue and approval state to the page.

const POST_TOOL = 'mcp__studio__post'
const NOTE_TOOL = 'mcp__studio__note'
const HEARTBEAT_MS = 5000
const READY_WAIT_MS = 5000
const SEND_TIMEOUT_MS = 2000
const OPEN_TIMEOUT_MS = 10_000
const END_WAIT_MS = 500
const ASK_TEXT_MAX = 200
const NOT_RUNNING = 'The Studio server is not running; the user starts it with /studio.'
const SKILL_NAME = /^[a-z0-9-]+$/

type ToolKind = 'post' | 'note'

type Request = { id: string; skill: string; [field: string]: unknown }

// One prompt the mod submitted: the page request's id and the text submitted, by which
// `turn.start` finds the turn that runs it.
type Entry = { id: string; text: string }

type Line =
  | { type: 'ready'; url: string }
  | { type: 'request'; request: Request }

// A call whose `tool.check` verdict was `ask`, until it settles or the main turn ends.
type Candidate = { tool: string; input: string; isAsked: boolean }

// The server's URL while it runs; undefined before /studio and after it exits.
let url: string | undefined
// Resolves with the URL once the server is ready; set from the first /studio until the server exits.
let starting: Promise<string> | undefined
// True once /studio answered that Studio is starting, so a later failure is told with a toast.
let isAnsweredStarting = false
let heartbeat: { cancel: () => void } | undefined
// The tool names `$.tool.register` answered, by kind.
const tools = new Map<string, ToolKind>()
// Submitted prompts that have not started, in order; the one running in the main loop, if it is one.
let pending: Entry[] = []
let running: Entry | null = null
let busy = false
// Calls that may wait for approval, by tool_use_id.
const candidates = new Map<string, Candidate>()
// Every POST to the server goes through this chain, so events reach the page in order.
let chain: Promise<unknown> = Promise.resolve()
// True once a POST got no answer in time: sends fail at once until a heartbeat is answered.
let isServerDown = false
// True from session.end on, so the server's exit then is not told as a failure.
let isEnding = false

// Builds the prompt that carries a page request to the agent.
function requestPrompt(request: Request): string {
  const skill = `studio:${request.skill}`

  return (
    `A request from the Studio page for the workspace skill \`${skill}\`. ` +
    `Load \`${skill}\` with the Skill tool and answer the request as that skill says.\n\n` +
    '```json\n' +
    `${JSON.stringify(request, null, 2)}\n` +
    '```\n\n' +
    `Answer the user in the Studio page with the \`${POST_TOOL}\` tool, and report progress there ` +
    `with the \`${NOTE_TOOL}\` tool.`
  )
}

function debug($: EngineInterface, text: string): void {
  $.ui.log(`studio: ${text}`, { to: 'debug' })
}

// One POST, bounded by SEND_TIMEOUT_MS; false when the server did not take it. Never throws.
async function post($: EngineInterface, address: string, path: string, body: string): Promise<boolean> {
  let isAnswered = false
  const fetched = $.http.fetch(`${address}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body,
  }).then(
    response => {
      isAnswered = true
      if (!response.ok) debug($, `POST ${path}: HTTP ${response.status}`)
      return response.ok
    },
    (error: unknown) => {
      isAnswered = true
      debug($, `POST ${path} failed: ${String(error)}`)
      return false
    },
  )
  const timeout = $.clock.sleep(SEND_TIMEOUT_MS).then(
    () => {
      if (!isAnswered) {
        debug($, `POST ${path}: no answer in ${SEND_TIMEOUT_MS} ms; the server counts as down`)
        isServerDown = true
      }
      return false
    },
    () => false,
  )

  return Promise.race([fetched, timeout])
}

// Queues a POST behind every earlier one; resolves with whether the server took it. A hook that
// only informs the page does not await it.
function send($: EngineInterface, path: string, body: unknown): Promise<boolean> {
  const address = url
  if (!address || isServerDown) return Promise.resolve(false)
  const text = JSON.stringify(body)
  const sent = chain.then(() => post($, address, path, text))
  chain = sent

  return sent
}

// The heartbeat goes beside the chain, so a queue of unanswered POSTs cannot hold it; an answered
// one says the server is up again.
async function beat($: EngineInterface): Promise<void> {
  const address = url
  if (!address) return
  if (!(await post($, address, '/heartbeat', '{}')) || !isServerDown) return
  isServerDown = false
  publishState($)
}

function event($: EngineInterface, body: Record<string, unknown>): Promise<boolean> {
  return send($, '/event', body)
}

// The current request: the one running, or while the session is idle the next to run.
function publishState($: EngineInterface): void {
  const shown = busy ? running : (pending[0] ?? null)
  const queued = pending.filter(entry => entry !== shown).map(entry => entry.id)
  void event($, { kind: 'state', busy, current: shown?.id ?? null, queued })
}

function forget($: EngineInterface, entry: Entry): void {
  pending = pending.filter(other => other !== entry)
  publishState($)
}

async function submit($: EngineInterface, entry: Entry): Promise<void> {
  pending.push(entry)
  publishState($)
  try {
    const result = await $.prompt.submit({ text: entry.text })
    if (result.drop !== undefined) {
      debug($, `prompt dropped: ${result.drop}`)
      forget($, entry)
    }
  } catch (error) {
    debug($, `prompt.submit failed: ${String(error)}`)
    forget($, entry)
  }
}

// The command that opens a URL in the default browser on this platform.
async function opener($: EngineInterface, address: string): Promise<string[]> {
  if ((await $.env.get('OS')) === 'Windows_NT') return ['cmd', '/c', 'start', '', address]
  const uname = await $.process.run(['uname', '-s'], { timeoutMs: OPEN_TIMEOUT_MS })

  return uname.stdout.trim() === 'Darwin' ? ['open', address] : ['xdg-open', address]
}

async function openPage($: EngineInterface, address: string): Promise<void> {
  try {
    const result = await $.process.run(await opener($, address), { timeoutMs: OPEN_TIMEOUT_MS })
    if (result.exitCode !== 0) debug($, `opening ${address} exited ${result.exitCode}: ${result.stderr}`)
  } catch (error) {
    debug($, `opening ${address} failed: ${String(error)}`)
  }
}

function parse($: EngineInterface, text: string): Line | undefined {
  try {
    const value = JSON.parse(text) as unknown
    if (typeof value === 'object' && value !== null && 'type' in value) return value as Line
    debug($, `stdout line without a type: ${text}`)
  } catch (error) {
    debug($, `stdout line is not JSON (${String(error)}): ${text}`)
  }

  return undefined
}

async function handle($: EngineInterface, line: Line, ready: (address: string) => void): Promise<void> {
  if (line.type === 'ready' && typeof line.url === 'string') {
    ready(line.url)
  } else if (line.type === 'request') {
    const request = line.request
    if (typeof request?.id !== 'string' || typeof request.skill !== 'string' || !SKILL_NAME.test(request.skill)) {
      debug($, `request without a valid id or skill: ${JSON.stringify(request)}`)
      return
    }
    await submit($, { id: request.id, text: requestPrompt(request) })
  } else {
    debug($, `unknown stdout line: ${JSON.stringify(line)}`)
  }
}

// Starts the server; the promise resolves with its URL once it printed `ready`, and rejects when
// it exits or fails before that. The read loop runs for the server's life.
function start($: EngineInterface): Promise<string> {
  isAnsweredStarting = false
  return new Promise((resolve, reject) => {
    const ready = (address: string): void => {
      if (url) return
      url = address
      isServerDown = false
      $.ui.status(`Studio: ${address}`)
      heartbeat = $.clock.every(HEARTBEAT_MS, () => void beat($))
      publishState($)
      resolve(address)
      void openPage($, address)
    }
    void (async () => {
      let buffer = ''
      let failure = 'it exited'
      try {
        const child = $.process.spawn({ argv: [`${$.plugin.root}/server/studio-server.sh`] })
        for await (const piece of child) {
          if (piece.stream === 'stderr') {
            debug($, piece.text.trimEnd())
            continue
          }
          buffer += piece.text
          let end = buffer.indexOf('\n')
          while (end >= 0) {
            const text = buffer.slice(0, end).trim()
            buffer = buffer.slice(end + 1)
            const line = text ? parse($, text) : undefined
            if (line) await handle($, line, ready)
            end = buffer.indexOf('\n')
          }
        }
      } catch (error) {
        failure = String(error)
      }
      debug($, `the server stopped: ${failure}`)
      const wasReady = url !== undefined
      url = undefined
      starting = undefined
      heartbeat?.cancel()
      heartbeat = undefined
      $.ui.status(undefined)
      if (isEnding) {
        if (!wasReady) reject(new Error(failure))
      } else if (wasReady) {
        $.ui.toast('The Studio server stopped; /studio starts it again.')
      } else {
        if (isAnsweredStarting) $.ui.toast(`Studio could not start: ${failure}`)
        reject(new Error(failure))
      }
    })()
  })
}

// A short description of a tool call for the approval notice.
function describeCall(input: unknown): string {
  const fields = (typeof input === 'object' && input !== null ? input : {}) as Record<string, unknown>
  for (const key of ['command', 'file_path', 'url', 'path', 'pattern', 'description']) {
    const value = fields[key]
    if (typeof value === 'string' && value) return value.slice(0, ASK_TEXT_MAX)
  }
  const text = JSON.stringify(input) ?? ''

  return text.length > ASK_TEXT_MAX ? `${text.slice(0, ASK_TEXT_MAX - 3)}...` : text
}

const isAskOpen = (): boolean => [...candidates.values()].some(candidate => candidate.isAsked)

// Ends one call's wait (by id) or every wait (no id); `ask-done` follows the last open ask.
function settle($: EngineInterface, id?: string): void {
  const wasOpen = isAskOpen()
  if (id === undefined) candidates.clear()
  else candidates.delete(id)
  if (wasOpen && !isAskOpen()) void event($, { kind: 'ask-done' })
}

function fieldOf(e: unknown, key: string): unknown {
  return (e as Record<string, unknown>)[key]
}

// Serves the mod's own tools.
async function serveTool($: EngineInterface, kind: ToolKind, e: unknown) {
  if (!url) return { deny: NOT_RUNNING }
  const text = String(fieldOf(e, 'text') ?? '')
  const images = fieldOf(e, 'images')
  const body =
    kind === 'post' ? { kind: 'agent', text, ...(Array.isArray(images) ? { images } : {}) } : { kind: 'note', text }
  if (!(await event($, body))) return { deny: 'The Studio server did not take the message.' }

  return { result: kind === 'post' ? 'Shown in the Studio page.' : 'Noted in the Studio page.' }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    isEnding = false
    await $.command.register({
      name: 'studio',
      description: 'Start the Studio page and open it in the browser',
    })
    const specs: { kind: ToolKind; description: string; inputSchema: Record<string, unknown> }[] = [
      {
        kind: 'post',
        description:
          'Shows an answer to the user in the Studio web page, with optional images. Use it to answer ' +
          'every request that came from the Studio page.',
        inputSchema: {
          type: 'object',
          properties: {
            text: { type: 'string', description: 'The message, plain text' },
            images: { type: 'array', items: { type: 'string' }, description: 'Absolute paths of images to show' },
          },
          required: ['text'],
        },
      },
      {
        kind: 'note',
        description: 'Shows a one-line progress note in the Studio web page while a request is carried out.',
        inputSchema: {
          type: 'object',
          properties: { text: { type: 'string', description: 'The note, plain text' } },
          required: ['text'],
        },
      },
    ]
    for (const spec of specs) {
      const registered = await $.tool.register({
        name: spec.kind,
        description: spec.description,
        inputSchema: spec.inputSchema,
        isDeferred: false,
      })
      tools.set(registered.tool, spec.kind)
    }

    return next(e)
  })

  on('command.run', { command: 'studio' }, async $ => {
    if (url) {
      void openPage($, url)
      return { text: `Studio is running at ${url}` }
    }
    starting ??= start($)
    const ready = starting.then(
      address => address,
      (error: unknown) => (error instanceof Error ? error : new Error(String(error))),
    )
    const waited = $.clock.sleep(READY_WAIT_MS).then(
      () => undefined,
      () => undefined,
    )
    const outcome = await Promise.race([ready, waited])
    if (typeof outcome === 'string') return { text: `Studio is running at ${outcome}` }
    if (outcome instanceof Error) return { text: `Studio could not start: ${outcome.message}` }
    isAnsweredStarting = true

    return { text: 'Studio is starting; the page opens in the browser when the server is ready.' }
  })

  on('tool.call', async ($, e, next) => {
    const kind = tools.get(e.tool)
    if (kind) return serveTool($, kind, e)
    try {
      return await next(e)
    } finally {
      settle($, e.tool_use_id)
    }
  }).catch(($, e, next) => (tools.has(e.tool) ? { deny: 'The Studio mod failed to serve the tool.' } : next(e)))

  // Records each call whose verdict is `ask` and that a person may answer; whether one is asked is
  // known at PermissionRequest. `approver` is `person` where a person can be asked; the testing kit
  // never sets it, and a main-loop call without it is taken as the person's too.
  on('tool.check', async ($, e, next) => {
    const verdict = await next(e)
    const isPersons = e.approver === 'person' || (e.approver === undefined && e.agentId === undefined)
    if (verdict.decision === 'ask' && isPersons && e.tool_use_id && !candidates.has(e.tool_use_id)) {
      candidates.set(e.tool_use_id, { tool: e.tool, input: JSON.stringify(e.input) ?? '', isAsked: false })
    }

    return verdict
  }).catch(($, e, next) => next(e))

  // Raised when the approval dialog is about to be shown; no settings hook beneath decided, so a
  // person is asked. Its input has no tool_use_id: the call is found by its tool and input.
  on('classic.PermissionRequest', async ($, e, next) => {
    const result = await next(e)
    if (result.decision !== undefined) return result
    const input = JSON.stringify(e.tool_input) ?? ''
    // Of several calls with this tool and input, the most recent is the one the dialog is for.
    for (const candidate of [...candidates.values()].reverse()) {
      if (candidate.isAsked || candidate.tool !== e.tool_name || candidate.input !== input) continue
      candidate.isAsked = true
      void event($, { kind: 'ask', tool: e.tool_name, text: describeCall(e.tool_input) })
      break
    }

    return result
  }).catch(($, e, next) => next(e))

  // Credits the main loop's turn to the submitted prompt it runs, if any; else a terminal turn.
  on('turn.start', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined) return result
    // The matched entry ran; every entry before it and every other the turn's text holds is gone.
    const runs = (entry: Entry): boolean => e.text === entry.text || e.text.includes(entry.text)
    const k = pending.findIndex(runs)
    const match = k >= 0 ? pending[k] : undefined
    if (match) {
      const gone = pending.filter((entry, i) => i <= k || runs(entry))
      pending = pending.filter(entry => !gone.includes(entry))
    }
    running = match ?? null
    busy = true
    publishState($)

    return result
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined) return result
    running = null
    busy = false
    settle($)
    publishState($)
    void event($, { kind: 'turn', reason: e.reason })

    return result
  })

  on('session.end', async ($, e, next) => {
    isEnding = true
    if (url) {
      const waited = $.clock.sleep(END_WAIT_MS).then(
        () => false,
        () => false,
      )
      await Promise.race([event($, { kind: 'ended' }), waited])
    }

    return next(e)
  })
}
