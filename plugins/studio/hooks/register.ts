import type { EngineInterface, Register } from 'claude-code'

// The Studio mod: starts the studio server, turns the page's requests into prompts, serves the
// tools the agent answers the page with, reports busy, queue and approval state and every event
// it sees (turns, subagents, tool calls, permission asks, the agent's text) to the page, and stops
// a request the user stops in the page.

const POST_TOOL = 'mcp__studio__post'
const NOTE_TOOL = 'mcp__studio__note'
const HEARTBEAT_MS = 5000
const READY_WAIT_MS = 5000
const SEND_TIMEOUT_MS = 2000
const OPEN_TIMEOUT_MS = 10_000
const END_WAIT_MS = 500
const ASK_TEXT_MAX = 200
// The most characters of one string an event carries (a tool input's field, a prompt, the agent's
// text); a longer one is cut and ends with `…`.
const TEXT_MAX = 4000
// The most characters of a failed call's error an event carries.
const ERROR_MAX = 200
// The input fields that describe a call for an approval, in order.
const ASK_KEYS = ['command', 'file_path', 'url', 'path', 'pattern', 'description']
// The keys of `tool.call`'s input that are not the tool's arguments.
const RESERVED = new Set(['tool', 'tool_use_id', 'agentId', 'requestMeta', 'consent'])
const NOT_RUNNING = 'The Studio server is not running; the user starts it with /studio.'
const SKILL_NAME = /^[a-z0-9-]+$/

type ToolKind = 'post' | 'note'

type Request = { id: string; skill: string; [field: string]: unknown }

// A page request the mod holds: its id, the request, and once submitted the prompt's text, by
// which `turn.start` finds the turn that runs it. `isStopped`: the user stopped it after it was
// submitted and before it started; its turn is ended as soon as it starts.
// `passed`: main-loop turns other than task notifications that started without running it.
type Entry = { id: string; request: Request; text?: string; isStopped?: boolean; passed?: number }

type Line =
  | { type: 'ready'; url: string }
  | { type: 'request'; request: Request }
  | { type: 'stop'; id: string }

// A call whose `tool.check` verdict was `ask`, until it settles or the main turn ends; `agentId`
// the subagent that made it.
type Candidate = { tool: string; input: string; isAsked: boolean; agentId?: string }

// The server's URL while it runs; undefined before /studio and after it exits.
let url: string | undefined
// Resolves with the URL once the server is ready; set from the first /studio until the server exits.
let starting: Promise<string> | undefined
// True once /studio answered that Studio is starting, so a later failure is told with a toast.
let isAnsweredStarting = false
let heartbeat: { cancel: () => void } | undefined
// The tool names `$.tool.register` answered, by kind.
const tools = new Map<string, ToolKind>()
// Requests not yet submitted, in order: the mod submits the next one only when the session is
// idle and no submitted one waits, so its prompt names the requests stopped before it.
let waiting: Entry[] = []
// Submitted prompts that have not started, in order; the one running in the main loop, if it is one.
let pending: Entry[] = []
let running: Entry | null = null
let busy = false
// The main loop's running turn, and when it started (ms since the epoch).
let turnId: string | undefined
let started: number | null = null
// Requests the user stopped since the last prompt the mod submitted, which names them.
let stopped: string[] = []
// True from the stop of a running request until a main-loop turn that is not a task notification
// (a later request's prompt, which names the stopped one, or a turn typed in the terminal):
// background subagents and commands outlive the aborted turn, and each one's notification would
// start a turn that carries the stopped work on, so those turns are ended too.
let isQuieting = false
const NOTIFICATION = '<task-notification>'
// A submitted prompt passed by this many turns (other than task notifications) counts as lost: the
// person took it back into the prompt box, or a hook rewrote it, and the queue goes on without it.
const LOST_AFTER = 2
// The request each subagent works for (null: none), by agent id: its spawner's.
const agents = new Map<string, string | null>()
// Spawns not yet resolved, in order: the prompt and the spawner's request. A subagent's first
// `turn.start` comes before its spawn resolves with its id, and is matched by its prompt.
let spawns: { prompt: string; request: string | null }[] = []
// Calls that may wait for approval, by tool_use_id.
const candidates = new Map<string, Candidate>()
// Every POST to the server goes through this chain, so events reach the page in order.
let chain: Promise<unknown> = Promise.resolve()
// True once a POST got no answer in time: sends fail at once until a heartbeat is answered.
let isServerDown = false
// True from session.end on, so the server's exit then is not told as a failure.
let isEnding = false

// Builds the prompt that carries a page request to the agent; it first names the requests the
// user stopped since the last one, whose turns ended without a word to the agent.
function requestPrompt(request: Request, stoppedIds: string[] = []): string {
  const skill = `studio:${request.skill}`
  const stop = stoppedIds.length
    ? `The user stopped the Studio request${stoppedIds.length > 1 ? 's' : ''} ${stoppedIds.join(', ')} in the page ` +
      'before it was done; it is not to be continued, and what it made is kept as it is.\n\n'
    : ''

  return (
    stop +
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
// only informs the page does not await it. A body still being built keeps its place in the chain.
function send($: EngineInterface, path: string, body: unknown): Promise<boolean> {
  const address = url
  const built = Promise.resolve(body)
  if (!address || isServerDown) {
    built.catch(() => undefined)
    return Promise.resolve(false)
  }
  const sent = chain.then(async () => {
    // Dropped while the server counts as down, so a backlog after a timeout drains at once.
    if (isServerDown) return false
    let text: string
    try {
      text = JSON.stringify(await built)
    } catch (error) {
      debug($, `an event could not be built: ${String(error)}`)
      return false
    }
    return post($, address, path, text)
  })
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

function event($: EngineInterface, body: Record<string, unknown> | Promise<Record<string, unknown>>): Promise<boolean> {
  return send($, '/event', body)
}

// The request a loop works for: a subagent's, else the one running in the main loop, else null.
function requestOf(agentId: string | undefined): string | null {
  if (agentId !== undefined && agents.has(agentId)) return agents.get(agentId) ?? null
  return running?.id ?? null
}

// One event of the log of a request (`request`, null for none), with the loop it came from
// (`agent`, null for the main loop) and `time` (ms since the epoch); sent in the order of the calls.
function log(
  $: EngineInterface,
  kind: string,
  agentId: string | undefined,
  fields: Record<string, unknown>,
): Promise<boolean> {
  return logAs($, kind, headOf(agentId), fields)
}

type Head = { request: string | null; agent: string | null }

const headOf = (agentId: string | undefined): Head => ({ request: requestOf(agentId), agent: agentId ?? null })

// As `log`, with the request and loop given (a call's, fixed at its start).
function logAs($: EngineInterface, kind: string, head: Head, fields: Record<string, unknown>): Promise<boolean> {
  return event(
    $,
    $.clock.now().then(time => ({ kind, ...head, time, ...fields })),
  )
}

// `text` cut to `max` characters, the last one `…` when cut.
function cut(text: string, max = TEXT_MAX): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

// A tool call's arguments for the page, in order: each string, and each object or array as its JSON,
// cut to what is left of TEXT_MAX characters for them all; one after they are used up is `…`.
function inputOf(e: unknown): Record<string, unknown> {
  const input: Record<string, unknown> = {}
  let left = TEXT_MAX
  for (const [key, value] of Object.entries(e as Record<string, unknown>)) {
    if (RESERVED.has(key) || value === undefined) continue
    if (value === null || typeof value === 'number' || typeof value === 'boolean') {
      input[key] = value
      continue
    }
    const text = typeof value === 'string' ? value : (JSON.stringify(value) ?? String(value))
    input[key] = left > 0 ? cut(text, left) : '…'
    left -= (input[key] as string).length
  }

  return input
}

const toolName = (tool: string): string => tool.replace(/^mcp__/, '')

// The current request: the one running, or while the session is idle the next to run; `started`
// is when the running one started. A stopped request is in neither.
function publishState($: EngineInterface): void {
  const live = [...pending.filter(entry => !entry.isStopped), ...waiting]
  const shown = busy ? running : (live[0] ?? null)
  const queued = live.filter(entry => entry !== shown).map(entry => entry.id)
  void event($, { kind: 'state', busy, current: shown?.id ?? null, queued, started: busy && shown ? started : null })
}

function forget($: EngineInterface, entry: Entry): void {
  pending = pending.filter(other => other !== entry)
  publishState($)
  void submitNext($)
}

// Submits the next waiting request while the session is idle and no submitted prompt waits; its
// prompt names the requests stopped since the last one.
async function submitNext($: EngineInterface): Promise<void> {
  if (busy || pending.some(entry => !entry.isStopped)) return
  const entry = waiting.shift()
  if (!entry) return
  entry.text = requestPrompt(entry.request, stopped)
  stopped = []
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
    waiting.push({ id: request.id, request })
    publishState($)
    await submitNext($)
  } else if (line.type === 'stop' && typeof line.id === 'string') {
    await stop($, line.id)
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

// Ends the main loop's turn `id`. Never throws.
async function endTurn($: EngineInterface, id: string): Promise<boolean> {
  try {
    await $.turn.abort({ turnId: id })
    return true
  } catch (error) {
    debug($, `turn.abort failed: ${String(error)}`)
    return false
  }
}

// The user's Stop of a request. The running one's turn ends now, the next prompt names it, and
// task-notification turns are ended until another turn starts. A request not yet submitted leaves
// the queue; one submitted that has not started is named by the next prompt and its turn ends as
// soon as it starts, since a submitted prompt cannot be withdrawn.
async function stop($: EngineInterface, id: string): Promise<void> {
  if (running?.id === id && turnId !== undefined) {
    // Recorded before the abort resolves, in case the engine completes the turn and starts the next
    // one first; undone when the abort fails.
    const wasQuieting = isQuieting
    const isNew = !stopped.includes(id)
    if (isNew) stopped.push(id)
    isQuieting = true
    if (await endTurn($, turnId)) {
      void event($, { kind: 'stopped', id })
    } else {
      if (isNew) stopped = stopped.filter(other => other !== id)
      isQuieting = wasQuieting
    }
    return
  }
  const held = waiting.find(entry => entry.id === id)
  const submitted = pending.find(entry => entry.id === id && !entry.isStopped)
  if (held) {
    waiting = waiting.filter(entry => entry !== held)
  } else if (submitted) {
    // It stays among the submitted prompts so its turn is found and ended; the next request goes on.
    submitted.isStopped = true
    if (!stopped.includes(id)) stopped.push(id)
  } else {
    debug($, `stop of a request neither running nor waiting: ${id}`)
    return
  }
  publishState($)
  void event($, { kind: 'stopped', id })
  void submitNext($)
}

// A short description of a tool call: the first of `keys` its input has, else the input as JSON.
function describeCall(input: unknown, keys: string[] = ASK_KEYS): string {
  const fields = (typeof input === 'object' && input !== null ? input : {}) as Record<string, unknown>
  for (const key of keys) {
    const value = fields[key]
    if (typeof value === 'string' && value) return cut(value, ASK_TEXT_MAX)
  }

  return cut(JSON.stringify(input) ?? '', ASK_TEXT_MAX)
}

const isAskOpen = (): boolean => [...candidates.values()].some(candidate => candidate.isAsked)

// Ends one call's wait (by id) or every wait (no id); `ask-done` follows the last open ask. A call
// that was asked and settles (`ok`: it ran without error) is sent as `answer`.
function settle($: EngineInterface, id?: string, ok?: boolean): void {
  const wasOpen = isAskOpen()
  if (id === undefined) {
    candidates.clear()
  } else {
    const candidate = candidates.get(id)
    if (candidate?.isAsked && ok !== undefined) {
      void log($, 'answer', candidate.agentId, { use: id, tool: toolName(candidate.tool), ok })
    }
    candidates.delete(id)
  }
  if (wasOpen && !isAskOpen()) void event($, { kind: 'ask-done' })
}

function fieldOf(e: unknown, key: string): unknown {
  return (e as Record<string, unknown>)[key]
}

// Serves the mod's own tools.
async function serveTool($: EngineInterface, kind: ToolKind, e: unknown) {
  if (!url) return { deny: NOT_RUNNING }
  const text = cut(String(fieldOf(e, 'text') ?? ''))
  const given = fieldOf(e, 'images')
  const images = Array.isArray(given) ? given.map(path => cut(String(path))) : undefined
  const agentId = fieldOf(e, 'agentId') as string | undefined
  const fields = kind === 'post' ? { text, ...(images ? { images } : {}) } : { text }
  if (!(await log($, kind === 'post' ? 'agent' : 'note', agentId, fields))) return { deny: 'The Studio server did not take the message.' }

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
    // The call's input fields are the event's own.
    const use = e.tool_use_id ?? null
    const tool = toolName(e.tool)
    const head = headOf(e.agentId)
    const begun = await $.clock.now()
    void logAs($, 'tool', head, { use, tool, input: inputOf(e) })
    let ok = false
    let error = ''
    try {
      const result = await next(e)
      ok = result.deny === undefined && !result.isError
      if (!ok) error = cut(String(result.deny ?? result.text ?? ''), ERROR_MAX)
      return result
    } catch (thrown) {
      error = cut(String(thrown), ERROR_MAX)
      throw thrown
    } finally {
      settle($, e.tool_use_id, ok)
      const fields = { use, tool, ok, ...(ok ? {} : { error }) }
      void event($, $.clock.now().then(time => ({ kind: 'tool-end', ...head, time, ms: time - begun, ...fields })))
    }
  }).catch(($, e, next) => (tools.has(e.tool) ? { deny: 'The Studio mod failed to serve the tool.' } : next(e)))

  // Records each call whose verdict is `ask` and that a person may answer; whether one is asked is
  // known at PermissionRequest. `approver` is `person` where a person can be asked; the testing kit
  // never sets it, and a main-loop call without it is taken as the person's too.
  on('tool.check', async ($, e, next) => {
    const verdict = await next(e)
    const isPersons = e.approver === 'person' || (e.approver === undefined && e.agentId === undefined)
    if (verdict.decision === 'ask' && isPersons && e.tool_use_id && !candidates.has(e.tool_use_id)) {
      candidates.set(e.tool_use_id, {
        tool: e.tool,
        input: JSON.stringify(e.input) ?? '',
        isAsked: false,
        agentId: e.agentId,
      })
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
    for (const [use, candidate] of [...candidates.entries()].reverse()) {
      if (candidate.isAsked || candidate.tool !== e.tool_name || candidate.input !== input) continue
      candidate.isAsked = true
      void log($, 'ask', candidate.agentId, { use, tool: toolName(e.tool_name), text: describeCall(e.tool_input) })
      break
    }

    return result
  }).catch(($, e, next) => next(e))

  // Credits the main loop's turn to the submitted prompt it runs, if any; else a terminal turn.
  on('turn.start', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined) {
      if (!agents.has(e.agentId)) {
        const spawn = spawns.find(other => other.prompt === e.text)
        agents.set(e.agentId, spawn ? spawn.request : (running?.id ?? null))
      }
      void log($, 'turn-start', e.agentId, {})
      return result
    }
    // The entries the turn's text holds ran, and every submitted entry before the first of them is
    // gone. The turn runs the first live one; a turn holding only stopped ones ends at once.
    const runs = (entry: Entry): boolean => !!entry.text && (e.text === entry.text || e.text.includes(entry.text))
    const k = pending.findIndex(runs)
    const held = pending.filter(runs)
    if (k >= 0) pending = pending.filter((entry, i) => i > k && !runs(entry))
    const match = held.find(entry => !entry.isStopped)
    turnId = e.turnId
    started = await $.clock.now()
    running = match ?? null
    busy = true
    publishState($)
    void log($, 'turn-start', undefined, running ? {} : { text: cut(e.text) })
    const isNotification = held.length === 0 && e.text.trimStart().startsWith(NOTIFICATION)
    if (held.length === 0 && !isNotification) {
      const lost = pending.filter(entry => (entry.passed = (entry.passed ?? 0) + 1) >= LOST_AFTER)
      if (lost.length > 0) {
        debug($, `submitted prompts never started, dropped: ${lost.map(entry => entry.id).join(', ')}`)
        pending = pending.filter(entry => !lost.includes(entry))
      }
    }
    if (held.length > 0 && !match) {
      // Requests the user stopped after they were submitted: their turn ends at once.
      void endTurn($, e.turnId)
    } else if (isQuieting && isNotification) {
      debug($, 'ending a task-notification turn after a stop')
      void $.turn.abort({ turnId: e.turnId }).catch((error: unknown) => debug($, `turn.abort failed: ${String(error)}`))
    } else {
      isQuieting = false
    }

    return result
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    const ended = { reason: e.reason, ms: e.durationMs }
    if (e.agentId !== undefined) {
      void log($, 'turn-end', e.agentId, ended)
      return result
    }
    void log($, 'turn-end', undefined, ended)
    running = null
    busy = false
    turnId = undefined
    started = null
    settle($)
    publishState($)
    void submitNext($)

    return result
  })

  // A subagent the Agent tool or a workflow started: its type, task and spawner. Its turns, calls
  // and text are logged under the request its spawner works for.
  on('agent.spawn', async ($, e, next) => {
    const spawn = { prompt: e.prompt, request: requestOf(e.parentAgentId) }
    spawns.push(spawn)
    let result
    try {
      result = await next(e)
    } finally {
      spawns = spawns.filter(other => other !== spawn)
    }
    const agentId = (result as { agentId?: string }).agentId
    if (agentId !== undefined) {
      agents.set(agentId, spawn.request)
      void log($, 'agent-start', agentId, {
        parent: e.parentAgentId ?? null,
        type: cut(e.subagentType, ASK_TEXT_MAX),
        description: cut(e.description, ASK_TEXT_MAX),
        background: e.background === true,
        prompt: cut(e.prompt),
      })
    }

    return result
  })

  // Each text block of the model's response, the main loop's and each subagent's.
  on('session.append', { door: 'response' }, ($, e, next) => {
    if (e.message.type === 'assistant') {
      const text = e.message.content
        .filter(block => block.type === 'text' && typeof block.text === 'string')
        .map(block => block.text as string)
        .join('\n\n')
        .trim()
      if (text) void log($, 'text', e.agentId, { text: cut(text) })
    }

    return next(e)
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
