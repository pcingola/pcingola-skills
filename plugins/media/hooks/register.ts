import type { EngineInterface, HookStream, ProcessSpawnChunk, ProcessSpawnResult, Register } from 'claude-code'

// The media mod: `/animate <folder>` starts the editor server of media:html-animation on an animation folder
// and opens its page. Each comment the server reports as a `request` line becomes a prompt, one at a time;
// the agent answers in the page with the `post` and `note` tools, which the mod forwards to the server, and
// the mod tells the server `done` when the prompt's turn ends. A `stop` line ends the running request.

const SERVER = 'skills/html-animation/server/html-animation-server.sh'
const READY_WAIT_MS = 8000
const SEND_TIMEOUT_MS = 3000
const OPEN_TIMEOUT_MS = 10_000
const TEXT_MAX = 20_000
// The tool names the server's prompt gives; replaced by the names `$.tool.register` answered.
const PROMPT_POST = 'mcp__media__post'
const PROMPT_NOTE = 'mcp__media__note'
const NOT_RUNNING = 'The animation editor is not running; the user starts it with /animate <folder>.'
const NOTIFICATION = '<task-notification>'
// A submitted prompt passed by this many turns (other than task notifications) counts as lost.
const LOST_AFTER = 2

type ToolKind = 'post' | 'note'

// A comment the mod holds: its id, the server's prompt, and once submitted the text that was submitted, by
// which `turn.start` finds the turn that runs it. `isStopped`: stopped after it was submitted and before it
// started. `passed`: main-loop turns that started without running it.
type Entry = { id: string; prompt: string; text?: string; isStopped?: boolean; passed?: number }

type Line =
  | { type: 'ready'; url: string }
  | { type: 'request'; id: string; prompt: string }
  | { type: 'stop'; id?: string }

// The running server: its folder, its URL once ready, and the stream whose end kills it.
type Server = { folder: string; url?: string; child?: HookStream<ProcessSpawnChunk, ProcessSpawnResult> }

let server: Server | undefined
let starting: Promise<string> | undefined
let isEnding = false
const tools = new Map<string, ToolKind>()
const names: Record<ToolKind, string> = { post: PROMPT_POST, note: PROMPT_NOTE }
let waiting: Entry[] = []
let pending: Entry[] = []
let running: Entry | null = null
let busy = false
let turnId: string | undefined
// Comments stopped since the last prompt the mod submitted, which names them.
let stopped: string[] = []
// True from a stop until a main-loop turn that is not a task notification: background work of the stopped
// turn would otherwise carry it on.
let isQuieting = false
// Every POST to the server goes through this chain, so messages reach the page in order.
let chain: Promise<unknown> = Promise.resolve()

function debug($: EngineInterface, text: string): void {
  $.ui.log(`media animate: ${text}`, { to: 'debug' })
}

const cut = (text: string, max = TEXT_MAX): string => (text.length > max ? `${text.slice(0, max - 1)}…` : text)

// The prompt of one comment: the server's text with the registered tool names, after a line naming the
// comments the user stopped since the last prompt.
function promptOf(entry: Entry, stoppedIds: string[]): string {
  const stop = stoppedIds.length
    ? `The user stopped the animation comment${stoppedIds.length > 1 ? 's' : ''} ${stoppedIds.join(', ')} in the ` +
      'editor page before it was done; it is not to be continued, and what it changed is kept as it is.\n\n'
    : ''
  return stop + entry.prompt.split(PROMPT_POST).join(names.post).split(PROMPT_NOTE).join(names.note)
}

// One POST to the server's `/api/agent`, after every earlier one; false when the server did not take it.
function send($: EngineInterface, body: Record<string, unknown>): Promise<boolean> {
  const address = server?.url
  if (!address) return Promise.resolve(false)
  const sent = chain.then(async () => {
    const fetched = $.http
      .fetch(`${address}api/agent`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      })
      .then(
        response => {
          if (!response.ok) debug($, `POST /api/agent: HTTP ${response.status}`)
          return response.ok
        },
        (error: unknown) => {
          debug($, `POST /api/agent failed: ${String(error)}`)
          return false
        },
      )
    const timeout = $.clock.sleep(SEND_TIMEOUT_MS).then(
      () => false,
      () => false,
    )
    return Promise.race([fetched, timeout])
  })
  chain = sent
  return sent
}

function forget($: EngineInterface, entry: Entry): void {
  pending = pending.filter(other => other !== entry)
  void submitNext($)
}

// Submits the next waiting comment while the session is idle and no submitted prompt waits.
async function submitNext($: EngineInterface): Promise<void> {
  if (busy || pending.some(entry => !entry.isStopped)) return
  const entry = waiting.shift()
  if (!entry) return
  entry.text = promptOf(entry, stopped)
  stopped = []
  pending.push(entry)
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

async function endTurn($: EngineInterface, id: string): Promise<boolean> {
  try {
    await $.turn.abort({ turnId: id })
    return true
  } catch (error) {
    debug($, `turn.abort failed: ${String(error)}`)
    return false
  }
}

// The user's stop of a comment (no id: the running one). The running one's turn ends now and the next prompt
// names it; one waiting leaves the queue; one submitted that has not started ends as soon as it starts.
async function stop($: EngineInterface, id: string | undefined): Promise<void> {
  const target = id ?? running?.id
  if (target === undefined) {
    debug($, 'stop with no running comment')
    return
  }
  if (running?.id === target && turnId !== undefined) {
    const wasQuieting = isQuieting
    const isNew = !stopped.includes(target)
    if (isNew) stopped.push(target)
    isQuieting = true
    if (!(await endTurn($, turnId))) {
      if (isNew) stopped = stopped.filter(other => other !== target)
      isQuieting = wasQuieting
    }
    return
  }
  const held = waiting.find(entry => entry.id === target)
  const submitted = pending.find(entry => entry.id === target && !entry.isStopped)
  if (held) {
    waiting = waiting.filter(entry => entry !== held)
  } else if (submitted) {
    submitted.isStopped = true
    if (!stopped.includes(target)) stopped.push(target)
  } else {
    debug($, `stop of a comment neither running nor waiting: ${target}`)
    return
  }
  void submitNext($)
}

async function handle($: EngineInterface, line: Line, ready: (address: string) => void): Promise<void> {
  if (line.type === 'ready' && typeof line.url === 'string') {
    ready(line.url)
  } else if (line.type === 'request') {
    if (typeof line.id !== 'string' || typeof line.prompt !== 'string' || !line.prompt) {
      debug($, `request without an id or a prompt: ${JSON.stringify(line)}`)
      return
    }
    waiting.push({ id: line.id, prompt: line.prompt })
    await submitNext($)
  } else if (line.type === 'stop') {
    await stop($, typeof line.id === 'string' ? line.id : undefined)
  } else {
    debug($, `unknown stdout line: ${JSON.stringify(line)}`)
  }
}

// Starts the server on `folder`; resolves with its URL once it printed `ready`, rejects when it exits before.
function start($: EngineInterface, folder: string): Promise<string> {
  const own: Server = { folder }
  server = own
  return new Promise((resolve, reject) => {
    const ready = (address: string): void => {
      if (own.url) return
      own.url = address
      $.ui.status(`Animation editor: ${address}`)
      resolve(address)
      void openPage($, address)
    }
    void (async () => {
      let buffer = ''
      let failure = 'it exited'
      try {
        const child = $.process.spawn({ argv: [`${$.plugin.root}/${SERVER}`, folder] })
        own.child = child
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
      debug($, `the server on ${folder} stopped: ${failure}`)
      const wasReady = own.url !== undefined
      if (server === own) {
        server = undefined
        starting = undefined
        $.ui.status(undefined)
        if (wasReady && !isEnding) $.ui.toast('The animation editor stopped; /animate <folder> starts it again.')
      }
      if (!wasReady) reject(new Error(failure))
    })()
  })
}

// Ends the running server; its read loop clears the state. The queue of a folder's comments goes with it.
async function stopServer($: EngineInterface): Promise<void> {
  const old = server
  if (!old) return
  server = undefined
  starting = undefined
  // The old server's comments go with it, so a later turn end sends no `done` to a new server.
  waiting = []
  pending = []
  running = null
  stopped = []
  $.ui.status(undefined)
  try {
    await old.child?.return({ code: null, signal: 'SIGTERM' })
  } catch (error) {
    debug($, `stopping the server failed: ${String(error)}`)
  }
}

function fieldOf(e: unknown, key: string): unknown {
  return (e as Record<string, unknown>)[key]
}

async function serveTool($: EngineInterface, kind: ToolKind, e: unknown) {
  if (!server?.url) return { deny: NOT_RUNNING }
  const text = cut(String(fieldOf(e, 'text') ?? ''))
  const given = fieldOf(e, 'images')
  const images = Array.isArray(given) ? given.map(path => cut(String(path), 4000)) : undefined
  const body: Record<string, unknown> = { type: kind, text, ...(running ? { id: running.id } : {}) }
  if (kind === 'post' && images) body.images = images
  if (!(await send($, body))) return { deny: 'The animation editor did not take the message.' }
  return { result: kind === 'post' ? 'Shown in the animation editor page.' : 'Noted in the animation editor page.' }
}

// The folder of `/animate <folder>`: the arguments as typed, quotes removed, resolved against the session's
// directory when relative.
async function folderOf($: EngineInterface, args: string): Promise<string> {
  let folder = args.trim()
  if (/^(['"]).*\1$/.test(folder)) folder = folder.slice(1, -1)
  if (folder === '~' || folder.startsWith('~/')) folder = `${(await $.env.get('HOME')) ?? ''}${folder.slice(1)}`
  if (!folder.startsWith('/')) folder = `${(await $.session.cwd()).replace(/\/+$/, '')}/${folder}`
  return folder.replace(/\/+$/, '') || '/'
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    isEnding = false
    await $.command.register({
      name: 'animate',
      description: 'Open the animation editor on an HTML animation folder: /animate <folder> (/animate stop ends it)',
    })
    const specs: { kind: ToolKind; description: string; inputSchema: Record<string, unknown> }[] = [
      {
        kind: 'post',
        description:
          'Shows an answer to the user in the animation editor page, with optional images. Use it to answer ' +
          'every comment that came from the animation editor page.',
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
        description: 'Shows a one-line progress note in the animation editor page while a comment is handled.',
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
      names[spec.kind] = registered.tool
    }
    return next(e)
  })

  on('command.run', { command: 'animate' }, async ($, e) => {
    const args = e.args.trim()
    if (args === 'stop') {
      if (!server) return { text: 'The animation editor is not running.' }
      await stopServer($)
      return { text: 'The animation editor stopped.' }
    }
    if (!args) {
      if (server?.url) {
        void openPage($, server.url)
        return { text: `The animation editor of ${server.folder} is running at ${server.url}` }
      }
      return { text: 'Usage: /animate <folder>, the folder of an HTML animation made with media:html-animation.' }
    }
    const folder = await folderOf($, args)
    if (server?.folder === folder && server.url) {
      void openPage($, server.url)
      return { text: `The animation editor of ${folder} is running at ${server.url}` }
    }
    if (server && server.folder !== folder) await stopServer($)
    starting ??= start($, folder)
    const ready = starting.then(
      address => address,
      (error: unknown) => (error instanceof Error ? error : new Error(String(error))),
    )
    const waited = $.clock.sleep(READY_WAIT_MS).then(
      () => undefined,
      () => undefined,
    )
    const outcome = await Promise.race([ready, waited])
    if (typeof outcome === 'string') return { text: `The animation editor of ${folder} is running at ${outcome}` }
    if (outcome instanceof Error) return { text: `The animation editor could not start: ${outcome.message}` }
    return { text: 'The animation editor is starting; the page opens in the browser when the server is ready.' }
  })

  on('tool.call', async ($, e, next) => {
    const kind = tools.get(e.tool)
    if (kind) return serveTool($, kind, e)
    return next(e)
  }).catch(($, e, next) => (tools.has(e.tool) ? { deny: 'The media mod failed to serve the tool.' } : next(e)))

  // Credits the main loop's turn to the submitted prompt it runs, if any.
  on('turn.start', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined) return result
    const runs = (entry: Entry): boolean => !!entry.text && (e.text === entry.text || e.text.includes(entry.text))
    const k = pending.findIndex(runs)
    const held = pending.filter(runs)
    if (k >= 0) pending = pending.filter((entry, i) => i > k && !runs(entry))
    const match = held.find(entry => !entry.isStopped)
    turnId = e.turnId
    running = match ?? null
    busy = true
    const isNotification = held.length === 0 && e.text.trimStart().startsWith(NOTIFICATION)
    if (held.length === 0 && !isNotification) {
      const lost = pending.filter(entry => (entry.passed = (entry.passed ?? 0) + 1) >= LOST_AFTER)
      if (lost.length > 0) {
        debug($, `submitted prompts never started, dropped: ${lost.map(entry => entry.id).join(', ')}`)
        pending = pending.filter(entry => !lost.includes(entry))
      }
    }
    if (held.length > 0 && !match) {
      void endTurn($, e.turnId)
    } else if (isQuieting && isNotification) {
      debug($, 'ending a task-notification turn after a stop')
      void endTurn($, e.turnId)
    } else {
      isQuieting = false
    }
    return result
  })

  // The end of the main loop's turn: the comment it ran is done, and the next one is submitted.
  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined) return result
    const finished = running
    running = null
    busy = false
    turnId = undefined
    // Only a turn that ended with the model's answer finishes its comment. A stopped, aborted, refused or failed
    // turn leaves the comment open, with a note in the page unless the user stopped it there.
    if (finished && e.reason === 'answer') {
      void send($, { type: 'done', id: finished.id })
    } else if (finished && !stopped.includes(finished.id)) {
      void send($, { type: 'note', id: finished.id, text: `The turn ended without finishing this comment (${e.reason}).` })
    }
    void submitNext($)
    return result
  })

  on('session.end', async ($, e, next) => {
    isEnding = true
    return next(e)
  })
}
