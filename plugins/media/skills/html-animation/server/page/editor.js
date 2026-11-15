// The animation editor page: plays the animation in a sandboxed iframe through the player's postMessage
// protocol (`ha:*`), marks a point or a rectangle on a paused frame in stage pixels, sends comments to the
// server, and shows the comments, the agent's posts and notes, and reloads the iframe at the same t on `change`.
'use strict'

const $ = id => document.getElementById(id)
const SVG = 'http://www.w3.org/2000/svg'
// A drag shorter than this many screen pixels is a click: a point mark.
const DRAG_MIN = 6
const STAGE_HEIGHT_SHARE = 0.72
const HITS_WAIT_MS = 2000
// Mark coordinates are kept to a tenth of a stage pixel.
const round1 = v => Math.round(v * 10) / 10

const view = {
  ready: false,
  title: '',
  width: 1920,
  height: 1080,
  duration: 0,
  chapters: [],
  t: 0,
  chapter: null,
  playing: false,
  reloads: 0,
  mark: null, // {point: {x, y}} or {rect: {x, y, w, h}}
  ids: [], // null while the player's answer to the last query is awaited
  qid: 0,
  comments: [],
  selected: null,
  sending: false,
}

const frame = $('anim')
const overlay = $('overlay')
const scrub = $('scrub')

function toPlayer(message) {
  if (frame.contentWindow) frame.contentWindow.postMessage(message, '*')
}

function loadFrame(t) {
  view.ready = false
  view.reloads += 1
  frame.src = `/anim/index.html?t=${t.toFixed(3)}&reload=${view.reloads}`
}

// Layout

function fitStage() {
  const stage = $('stage')
  const ratio = view.width / view.height
  const room = stage.parentElement.clientWidth
  const width = Math.min(room, window.innerHeight * STAGE_HEIGHT_SHARE * ratio)
  stage.style.width = `${Math.floor(width)}px`
  stage.style.aspectRatio = `${view.width} / ${view.height}`
  overlay.setAttribute('viewBox', `0 0 ${view.width} ${view.height}`)
}

function fmt(t) {
  return (Math.round(t * 100) / 100).toFixed(2)
}

function chapterAt(t) {
  return view.chapters.find(c => t >= c.start && t < c.start + c.duration) ?? view.chapters[view.chapters.length - 1]
}

function renderTime() {
  $('time').textContent = `${fmt(view.t)} / ${fmt(view.duration)} s`
  $('play').textContent = view.playing ? 'Pause' : 'Play'
  overlay.classList.toggle('playing', view.playing)
  if (document.activeElement !== scrub) scrub.value = String(view.t)
  const now = view.chapter ?? chapterAt(view.t)?.id ?? null
  $('chapter-now').textContent = now ? `chapter ${now}` : ''
  for (const button of $('chapters').children) button.classList.toggle('now', button.dataset.id === now)
}

function renderChapters() {
  const bar = $('chapters')
  bar.replaceChildren()
  for (const chapter of view.chapters) {
    const button = document.createElement('button')
    button.type = 'button'
    button.dataset.id = chapter.id
    button.style.flex = `${chapter.duration} 1 0`
    button.textContent = chapter.title || chapter.id
    button.title = `${chapter.title || chapter.id}: ${fmt(chapter.start)} to ${fmt(chapter.start + chapter.duration)} s`
    // Just after the start: at a chapter's start time the previous chapter shows its finished state.
    button.addEventListener('click', () => seek(chapter.start + 0.001))
    bar.append(button)
  }
  scrub.max = String(view.duration || 1)
}

function renderMarkers() {
  const lane = $('markers')
  lane.replaceChildren()
  if (!view.duration) return
  for (const comment of view.comments) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = comment.state === 'done' ? 'done' : 'open'
    button.style.left = `${Math.min(100, (comment.t / view.duration) * 100)}%`
    button.title = `${fmt(comment.t)} s: ${comment.message}`
    button.dataset.id = comment.id
    button.addEventListener('click', () => select(comment.id))
    lane.append(button)
  }
}

function renderOverlay() {
  overlay.replaceChildren()
  const draw = (mark, isOld) => {
    if (mark?.point) {
      const ring = document.createElementNS(SVG, 'circle')
      ring.setAttribute('cx', mark.point.x)
      ring.setAttribute('cy', mark.point.y)
      ring.setAttribute('r', Math.max(14, view.width / 80))
      ring.setAttribute('class', `point${isOld ? ' old' : ''}`)
      overlay.append(ring)
    } else if (mark?.rect) {
      const box = document.createElementNS(SVG, 'rect')
      for (const key of ['x', 'y']) box.setAttribute(key, mark.rect[key])
      box.setAttribute('width', mark.rect.w)
      box.setAttribute('height', mark.rect.h)
      box.setAttribute('class', `rect${isOld ? ' old' : ''}`)
      overlay.append(box)
    }
  }
  const selected = view.comments.find(c => c.id === view.selected)
  if (selected && !view.mark) draw(selected.mark, true)
  draw(view.mark, false)
}

function renderCompose() {
  const mark = view.mark
  $('mark-info').textContent = !mark
    ? 'No mark.'
    : mark.point
      ? `Point at ${Math.round(mark.point.x)}, ${Math.round(mark.point.y)} at t = ${fmt(view.t)} s`
      : `Rectangle ${Math.round(mark.rect.x)}, ${Math.round(mark.rect.y)}, ${Math.round(mark.rect.w)} x ${Math.round(mark.rect.h)} at t = ${fmt(view.t)} s`
  $('ids-info').textContent = !mark
    ? ''
    : view.ids === null
      ? 'Finding the elements under the mark.'
      : view.ids.length
        ? `ids: ${view.ids.join(', ')}`
        : 'ids: none'
  $('send').disabled = !mark || view.ids === null || view.sending || !$('message').value.trim()
}

function renderComments() {
  const list = $('comments')
  list.replaceChildren()
  for (const comment of [...view.comments].reverse()) {
    const item = document.createElement('li')
    item.dataset.id = comment.id
    item.classList.toggle('selected', comment.id === view.selected)
    const meta = document.createElement('div')
    meta.className = 'meta'
    const state = document.createElement('span')
    const isStopped = comment.state === 'open' && comment.stopped
    state.className = `state ${isStopped ? 'stopped' : comment.state}`
    state.textContent = isStopped ? 'stopped' : comment.state
    meta.append(state, ` ${fmt(comment.t)} s${comment.chapter ? `, ${comment.chapter}` : ''}`)
    if (comment.state === 'open' && !comment.stopped) {
      // An open comment is queued or running; its Stop drops it from the queue or ends its turn.
      const stop = document.createElement('button')
      stop.type = 'button'
      stop.className = 'button danger small stop'
      stop.textContent = 'Stop'
      stop.title = 'Stop this comment: drop it from the queue, or end the agent turn that handles it'
      stop.addEventListener('click', event => {
        event.stopPropagation()
        stopComment(comment.id, stop)
      })
      meta.append(stop)
    }
    const text = document.createElement('div')
    text.className = 'msg-text'
    text.textContent = comment.message
    item.append(meta, text)
    if (comment.answer) {
      const answer = document.createElement('div')
      answer.className = 'answer'
      answer.textContent = comment.answer
      item.append(answer)
    }
    item.addEventListener('click', () => select(comment.id))
    list.append(item)
  }
  renderMarkers()
}

async function stopComment(id, button) {
  button.disabled = true
  try {
    await api('/api/stop', { id })
    $('send-status').textContent = `Stop sent for ${id}.`
  } catch (error) {
    button.disabled = false
    $('send-status').textContent = `Stop failed: ${error.message}`
  }
}

function addMessage(kind, message) {
  const item = document.createElement('li')
  item.className = kind
  const meta = document.createElement('div')
  meta.className = 'meta'
  const when = message.time ? new Date(message.time * 1000).toLocaleTimeString() : ''
  meta.textContent = `${kind}${message.id ? ` (${message.id})` : ''} ${when}`
  const text = document.createElement('div')
  text.className = 'msg-text'
  text.textContent = message.text
  item.append(meta, text)
  for (const image of message.images ?? []) {
    if (image.url) {
      const img = document.createElement('img')
      img.src = image.url
      img.alt = image.path
      item.append(img)
    } else {
      const path = document.createElement('div')
      path.className = 'meta'
      path.textContent = image.path
      item.append(path)
    }
  }
  $('messages').prepend(item)
}

// Player control

function seek(t) {
  toPlayer({ type: 'ha:pause' })
  toPlayer({ type: 'ha:seek', t: Math.max(0, Math.min(view.duration || t, t)) })
}

function togglePlay() {
  if (view.playing) {
    toPlayer({ type: 'ha:pause' })
  } else {
    clearMark()
    toPlayer({ type: 'ha:play' })
  }
}

function select(id) {
  const comment = view.comments.find(c => c.id === id)
  if (!comment) return
  view.selected = id
  view.mark = null
  view.ids = []
  seek(comment.t)
  renderComments()
  renderOverlay()
  renderCompose()
}

function clearMark() {
  view.mark = null
  view.ids = []
  renderOverlay()
  renderCompose()
}

// Marking: overlay pixels to stage pixels through the SVG's own box.

function stagePoint(event) {
  const box = overlay.getBoundingClientRect()
  return {
    x: round1(Math.max(0, Math.min(view.width, ((event.clientX - box.left) / box.width) * view.width))),
    y: round1(Math.max(0, Math.min(view.height, ((event.clientY - box.top) / box.height) * view.height))),
    sx: event.clientX,
    sy: event.clientY,
  }
}

let drag = null

overlay.addEventListener('pointerdown', event => {
  if (!view.ready) return
  if (view.playing) {
    toPlayer({ type: 'ha:pause' })
    return
  }
  event.preventDefault()
  overlay.setPointerCapture(event.pointerId)
  drag = stagePoint(event)
  view.selected = null
  view.mark = { point: { x: drag.x, y: drag.y } }
  view.ids = []
  renderOverlay()
})

overlay.addEventListener('pointermove', event => {
  if (!drag) return
  const p = stagePoint(event)
  if (Math.hypot(p.sx - drag.sx, p.sy - drag.sy) < DRAG_MIN) return
  view.mark = {
    rect: {
      x: Math.min(drag.x, p.x),
      y: Math.min(drag.y, p.y),
      w: round1(Math.abs(p.x - drag.x)),
      h: round1(Math.abs(p.y - drag.y)),
    },
  }
  renderOverlay()
})

overlay.addEventListener('pointerup', () => {
  if (!drag) return
  drag = null
  if (view.mark?.rect && (view.mark.rect.w < 1 || view.mark.rect.h < 1)) {
    view.mark = { point: { x: view.mark.rect.x, y: view.mark.rect.y } }
  }
  view.qid += 1
  view.ids = null
  toPlayer({ type: 'ha:query', qid: view.qid, ...view.mark })
  // A player that does not answer leaves the comment with no ids instead of blocking it.
  const qid = view.qid
  setTimeout(() => {
    if (view.qid === qid && view.ids === null) {
      view.ids = []
      renderCompose()
    }
  }, HITS_WAIT_MS)
  renderOverlay()
  renderComments()
  renderCompose()
  $('message').focus()
})

// Messages from the player

window.addEventListener('message', event => {
  if (event.source !== frame.contentWindow) return
  const data = event.data
  if (!data || typeof data.type !== 'string' || !data.type.startsWith('ha:')) return
  if (data.type === 'ha:ready') {
    view.ready = true
    view.title = data.title ?? ''
    view.width = data.width || view.width
    view.height = data.height || view.height
    view.duration = data.duration ?? 0
    view.chapters = data.chapters ?? []
    $('title').textContent = view.title || 'Animation'
    document.title = `${view.title || 'Animation'} editor`
    fitStage()
    renderChapters()
    renderComments()
    renderOverlay()
    renderTime()
  } else if (data.type === 'ha:time') {
    view.t = data.t
    view.chapter = data.chapter ?? null
    view.playing = !!data.playing
    renderTime()
  } else if (data.type === 'ha:hits' && data.qid === view.qid) {
    view.ids = Array.isArray(data.ids) ? data.ids : []
    if (typeof data.chapter === 'string') view.chapter = data.chapter
    renderCompose()
  }
})

// Server

async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const value = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`)
  return value
}

function upsert(comment) {
  const k = view.comments.findIndex(c => c.id === comment.id)
  if (k >= 0) view.comments[k] = comment
  else view.comments.push(comment)
  renderComments()
}

$('compose').addEventListener('submit', async event => {
  event.preventDefault()
  if (!view.mark || view.ids === null || view.sending) return
  const message = $('message').value.trim()
  if (!message) return
  view.sending = true
  $('send-status').textContent = 'Rendering the marked frame and sending.'
  renderCompose()
  try {
    const comment = await api('/api/comment', {
      t: view.t,
      chapter: view.chapter ?? chapterAt(view.t)?.id ?? null,
      mark: view.mark,
      ids: view.ids,
      message,
    })
    upsert(comment)
    $('message').value = ''
    $('send-status').textContent = `Sent as ${comment.id}.`
    view.selected = comment.id
    clearMark()
    renderComments()
  } catch (error) {
    $('send-status').textContent = `Not sent: ${error.message}`
  } finally {
    view.sending = false
    renderCompose()
  }
})

$('message').addEventListener('input', renderCompose)
$('clear').addEventListener('click', clearMark)
$('play').addEventListener('click', togglePlay)
scrub.addEventListener('input', () => {
  clearMark()
  seek(Number(scrub.value))
})
window.addEventListener('resize', fitStage)
document.addEventListener('keydown', event => {
  if (event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLInputElement) return
  if (event.code === 'Space') {
    event.preventDefault()
    togglePlay()
  } else if (event.code === 'Escape') {
    clearMark()
  }
})

function connect() {
  const source = new EventSource('/api/events')
  source.addEventListener('open', () => {
    $('link').textContent = 'connected'
    $('link').classList.add('on')
  })
  source.addEventListener('error', () => {
    $('link').textContent = 'disconnected'
    $('link').classList.remove('on')
  })
  source.addEventListener('change', () => {
    clearMark()
    loadFrame(view.t)
  })
  source.addEventListener('comment', event => upsert(JSON.parse(event.data).comment))
  source.addEventListener('post', event => addMessage('post', JSON.parse(event.data)))
  source.addEventListener('note', event => addMessage('note', JSON.parse(event.data)))
}

async function start() {
  try {
    const state = await api('/api/state')
    view.comments = state.comments ?? []
    $('folder').textContent = state.folder ?? ''
    const animation = state.animation ?? {}
    if (animation.width && animation.height) {
      view.width = animation.width
      view.height = animation.height
    }
    for (const message of state.messages ?? []) addMessage(message.kind, message)
  } catch (error) {
    $('send-status').textContent = `State not read: ${error.message}`
  }
  fitStage()
  renderComments()
  renderCompose()
  connect()
  loadFrame(0)
}

start()
