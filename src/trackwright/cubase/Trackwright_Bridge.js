// Trackwright Bridge - MIDI Remote script for Cubase (ES5 only).
// Part of the Trackwright project. Installed with `trackwright script install`.
// Request/response bridge between the Trackwright Python bridge and the Cubase MIDI Remote API.
// Derived from the cubase-mcp-poc script 0.2.2, whose behaviour was verified on Cubase Elements 15.0.30.
//
// Ports (named from Cubase's point of view; created as virtual ports by Python):
//   MIDI input  <- "Trackwright To Cubase"   (Python virtual OUTPUT)
//   MIDI output -> "Trackwright From Cubase" (Python virtual INPUT)
//
// Frame (SysEx, every data byte 0..127):
//   F0 7D 54 57 <ver> <seqHi> <seqLo> <fragIdx> <fragCount> <ascii payload...> F7   ("TW" tag)
// Payload: JSON (ASCII; non-ASCII escaped as \uXXXX), split into fragments.
//
// Requests that need DirectAccess are queued in mOnSysex (which has no activeMapping)
// and executed in page.mOnIdle(activeDevice, activeMapping).

var midiremote_api = require('midiremote_api_v1')

var SCRIPT_VERSION = '1.3.0'
var PROTOCOL_VERSION = 1
var MANUFACTURER = 0x7D
var MAGIC_A = 0x54
var MAGIC_B = 0x57
var HEADER_LEN = 9
var MAX_FRAGMENT_PAYLOAD = 240
var MAX_FRAGMENTS = 64
var MAX_PENDING_ASSEMBLIES = 8
var MAX_QUEUE = 32
var MAX_OPS_PER_IDLE = 4
var DUP_CACHE_SIZE = 64
var ASSEMBLY_MAX_IDLE_TICKS = 2000
// Write policy lives in the Python server (configurable allow-list, dry runs). The script only checks
// object validity and optional caller preconditions (expectChannelTitle, expectTitle).
var GUARD_MAX_NODES = 3000
var GUARD_MAX_DEPTH = 8
var MAX_EVENTS = 500

var deviceDriver = midiremote_api.makeDeviceDriver('Trackwright', 'Bridge', 'Trackwright')

var midiInput = deviceDriver.mPorts.makeMidiInput('Trackwright To Cubase')
var midiOutput = deviceDriver.mPorts.makeMidiOutput('Trackwright From Cubase')

deviceDriver.makeDetectionUnit().detectPortPair(midiInput, midiOutput)
	.expectInputNameEquals('Trackwright To Cubase')
	.expectOutputNameEquals('Trackwright From Cubase')

// Status panel on the MIDI Remote surface (TW-1101). Only mechanisms verified in Cubase 15 are used:
// fixed label text, a label bound to the selected track and a lamp driven by the script. Dynamic text
// through relateTo + setDisplayValue did NOT display (experiment of 2026-11-13) and is not used.
var PANEL_ENABLED = true

// Automation controls (TW-1206/TW-1207). Surface faders bound to parameters of the selected track, whose
// touch state the script drives: moving a *touched* surface control is how hardware controllers write
// automation in Touch mode (verified for volume, variant B2, 2026-11-13). Off in released builds;
// experiments/tw1206/build.py switches them on.
var AUTOMATION_CONTROLS_ENABLED = false

// Without the panel a single element is still needed for Cubase to show the surface.
if (!PANEL_ENABLED) deviceDriver.mSurface.makeLabelField(0, 0, 4, 1)

var page = deviceDriver.mMapping.makePage('Bridge')

// ---------------------------------------------------------------- state
var state = {
	sessionId: '',
	loadedAt: 0,
	seqOut: 0,
	deviceActive: false,
	pageActive: false,
	daActive: false,
	daMixActive: false,
	idleTicks: 0,
	deviceIdleTicks: 0,
	sysexIn: 0,
	framesRejected: 0,
	lastError: '',
	assemblies: {},
	assemblyCount: 0,
	queue: [],
	dupKeys: [],
	dupMap: {},
	// sid/rid of requests queued for idle and not answered yet (0.1.3: in-flight duplicate suppression)
	inflight: {},
	dupInFlightDropped: 0,
	events: [],
	eventsDropped: 0,
	eventSeq: 0,
	removedObjects: 0,
	changedObjects: 0,
	changedParameters: 0
}

function makeSessionId() {
	var s = ''
	var chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
	for (var i = 0; i < 12; i++) {
		s += chars.charAt(Math.floor(Math.random() * chars.length))
	}
	return s
}

state.sessionId = makeSessionId()
state.loadedAt = (new Date()).getTime()

// ---------------------------------------------------------------- status panel (TW-1101)
// Layout (grid units): row 0 = "Trackwright <version>" + activity lamp, row 1 = selected track name.
// The lamp lights when a request arrives and goes off once the queue is empty, after at least
// PANEL_LAMP_MIN_TICKS idle ticks so that it is visible. Every call is guarded: a surface problem must
// never stop the script from loading or answering.
var panel = null
var PANEL_LAMP_MIN_TICKS = 3 // ~0.3 s at the measured ~8.9 idle ticks per second
function buildPanel() {
	if (!PANEL_ENABLED) return
	try {
		var surface = deviceDriver.mSurface
		panel = { lampOn: false, lampOffAt: 0, errors: [] }
		panel.title = surface.makeLabelField(0, 0, 8, 1)
		panel.lamp = surface.makeLamp(8, 0, 1, 1)
		panel.track = surface.makeLabelField(0, 1, 9, 1)
	} catch (e) {
		state.lastError = 'panel build: ' + String(e)
		panel = null
		return
	}
	try { panel.lamp.setShapeCircle() } catch (e1) { panel.errors.push('lamp shape: ' + String(e1)) }
	try { page.setLabelFieldText(panel.title, 'Trackwright ' + SCRIPT_VERSION) } catch (e2) { panel.errors.push('title: ' + String(e2)) }
	try {
		page.setLabelFieldHostObject(panel.track, page.mHostAccess.mTrackSelection.mMixerChannel)
	} catch (e3) { panel.errors.push('track: ' + String(e3)) }
}
function panelLamp(activeDevice, on) {
	if (!panel || panel.lampOn === on) return
	panel.lampOn = on
	try { panel.lamp.mSurfaceValue.setProcessValue(activeDevice, on ? 1 : 0) } catch (e) { panel.errors.push('lamp: ' + String(e)) }
}
function panelActivity(activeDevice) {
	if (!panel) return
	panel.lampOffAt = state.idleTicks + PANEL_LAMP_MIN_TICKS
	panelLamp(activeDevice, true)
}
function panelIdle(activeDevice) {
	if (panel && panel.lampOn && state.queue.length === 0 && state.idleTicks >= panel.lampOffAt) panelLamp(activeDevice, false)
}
buildPanel()

// ---------------------------------------------------------------- automation controls (TW-1206/1207)
// One surface fader per bindable parameter of the selected channel. Each control caches the value,
// display text and titles that Cubase reports for it, so the bound parameter can be identified (the
// titles name it, which matters for plugin parameter banks whose order is decided by Cubase).
var autoControls = null
var AUTO_INSERT_SLOTS = 2
var AUTO_BANK_SIZE = 8
function buildAutomationControls() {
	if (!AUTOMATION_CONTROLS_ENABLED) return
	autoControls = { list: [], byKey: {}, errors: [] }
	var ch = null
	try { ch = page.mHostAccess.mTrackSelection.mMixerChannel } catch (e) { autoControls.errors.push('channel: ' + String(e)); return }
	var targets = [
		['volume', function () { return ch.mValue.mVolume }],
		['pan', function () { return ch.mValue.mPan }]
	]
	for (var si = 0; si < 4; si++) {
		(function (i) { targets.push(['send' + (i + 1) + '.level', function () { return ch.mSends.getByIndex(i).mLevel }]) })(si)
	}
	var bands = ['mBand1', 'mBand2', 'mBand3', 'mBand4']
	for (var bi = 0; bi < bands.length; bi++) {
		(function (b, n) {
			targets.push(['eq' + n + '.gain', function () { return ch.mChannelEQ[b].mGain }])
			targets.push(['eq' + n + '.freq', function () { return ch.mChannelEQ[b].mFreq }])
			targets.push(['eq' + n + '.q', function () { return ch.mChannelEQ[b].mQ }])
		})(bands[bi], bi + 1)
	}
	targets.push(['prefilter.gain', function () { return ch.mPreFilter.mGain }])
	targets.push(['prefilter.lowcut', function () { return ch.mPreFilter.mLowCutFreq }])
	targets.push(['prefilter.highcut', function () { return ch.mPreFilter.mHighCutFreq }])
	for (var qi = 0; qi < 8; qi++) {
		(function (i) { targets.push(['qc' + (i + 1), function () { return ch.mQuickControls.getByIndex(i) }]) })(qi)
	}
	for (var slot = 0; slot < AUTO_INSERT_SLOTS; slot++) {
		var bank = null
		try {
			bank = ch.mInsertAndStripEffects.makeInsertEffectViewer('trackwright-insert-' + (slot + 1)).accessSlotAtIndex(slot).mParameterBankZone
		} catch (e1) { autoControls.errors.push('insert viewer ' + (slot + 1) + ': ' + String(e1)) }
		for (var pi = 0; pi < AUTO_BANK_SIZE && bank; pi++) {
			(function (z, s1, p1) { targets.push(['insert' + s1 + '.p' + p1, function () { return z.makeParameterValue() }]) })(bank, slot + 1, pi + 1)
		}
	}
	for (var ti = 0; ti < targets.length; ti++) addAutomationControl(targets[ti][0], targets[ti][1], ti)
}
function addAutomationControl(key, hostValue, index) {
	var c = { key: key, touched: false, value: null, display: null, title: null, errors: [] }
	try {
		c.fader = deviceDriver.mSurface.makeFader(10 + (index % 16), 2 * Math.floor(index / 16), 1, 2)
		c.touch = deviceDriver.mSurface.makeCustomValueVariable('autoTouch.' + key)
	} catch (e) { autoControls.errors.push(key + ' element: ' + String(e)); return }
	try { page.makeValueBinding(c.fader.mSurfaceValue, hostValue()) } catch (e1) { c.errors.push('binding: ' + String(e1)) }
	try {
		if (c.fader.mSurfaceValue.mTouchState) c.fader.mSurfaceValue.mTouchState.bindTo(c.touch)
		else c.errors.push('mTouchState not available')
	} catch (e2) { c.errors.push('touch binding: ' + String(e2)) }
	try {
		c.fader.mSurfaceValue.mOnProcessValueChange = function (activeDevice, value) { c.value = value }
		c.fader.mSurfaceValue.mOnDisplayValueChange = function (activeDevice, value, units) { c.display = units ? value + ' ' + units : value }
		c.fader.mSurfaceValue.mOnTitleChange = function (activeDevice, objectTitle, valueTitle) { c.title = objectTitle + ' / ' + valueTitle }
	} catch (e3) { c.errors.push('callbacks: ' + String(e3)) }
	autoControls.list.push(c)
	autoControls.byKey[key] = c
}
function describeControl(c) {
	return { key: c.key, value: c.value, display: c.display, title: c.title, touched: c.touched, errors: c.errors.slice(-3) }
}
buildAutomationControls()

var hasJSON = (typeof JSON !== 'undefined' && typeof JSON.parse === 'function' && typeof JSON.stringify === 'function')

// Two DirectAccess instances (0.2.0):
//   'selected': base = selected track channel (verified in 0.1.x)
//   'mixer'   : base = mix console (forum report: walks every mixer channel; to be verified)
// `da` always points to the instance of the request being executed (set in runQueued).
var daSel = null
var daMix = null
var daError = ''
var daMixError = ''
try {
	if (page.mHostAccess.makeDirectAccess) {
		daSel = page.mHostAccess.makeDirectAccess(page.mHostAccess.mTrackSelection.mMixerChannel)
	} else {
		daError = 'makeDirectAccess not available'
	}
} catch (e) {
	daError = 'makeDirectAccess threw: ' + String(e)
	daSel = null
}
try {
	if (page.mHostAccess.makeDirectAccess) daMix = page.mHostAccess.makeDirectAccess(page.mHostAccess.mMixConsole)
} catch (e) {
	daMixError = 'makeDirectAccess(mMixConsole) threw: ' + String(e)
	daMix = null
}
var da = daSel

// ---------------------------------------------------------------- transport (0.2.0)
// Values arrive through callbacks; the script caches them so reads need no activeMapping.
var transport = {
	primary: { locator: null, cycleLeft: null, cycleRight: null },
	secondary: { locator: null, cycleLeft: null, cycleRight: null },
	tempoBPM: null,
	updates: 0
}
var TIME_FIELDS = { locator: 'mTransportLocator', cycleLeft: 'mCycleLocatorLeft', cycleRight: 'mCycleLocatorRight' }
var timeDisplay = null
try { timeDisplay = page.mHostAccess.mTransport.mTimeDisplay } catch (e) { timeDisplay = null }
function hookTime(displayName, field) {
	var obj = timeDisplay[displayName === 'primary' ? 'mPrimary' : 'mSecondary'][TIME_FIELDS[field]]
	obj.mOnChange = function (activeDevice, activeMapping, time, format) {
		transport[displayName][field] = { time: time, format: format, ms: (new Date()).getTime() }
		transport.updates++
	}
}
if (timeDisplay) {
	try {
		var dn = ['primary', 'secondary']
		for (var di = 0; di < dn.length; di++) {
			for (var tf in TIME_FIELDS) if (TIME_FIELDS.hasOwnProperty(tf)) hookTime(dn[di], tf)
		}
		timeDisplay.mOnChangeTempoBPM = function (activeDevice, activeMapping, bpm) {
			transport.tempoBPM = bpm
			transport.updates++
		}
	} catch (e) {
		state.lastError = 'transport hooks: ' + String(e)
	}
}

// ---------------------------------------------------------------- commands
// Each command gets a custom value variable bound with page.makeCommandBinding. Setting the
// variable to 1 (and back to 0 on the next idle tick) triggers the command (verified in the POC).
// The keys must match trackwright/commands.py, which also records how each command behaves.
var COMMANDS = [
	// Exact (category, name) from the "click to copy" snippets of the official list
	// https://steinbergmedia.github.io/midiremote_api_doc/examples/commandbindings/ (headed Cubase/Nuendo 13).
	// Verified (POC): the category is 'AddTrack' (no space); 'Add Track' gives canPerform=false.
	['zoom.in', 'Zoom', 'Zoom In'],
	['zoom.out', 'Zoom', 'Zoom Out'],
	['edit.undo', 'Edit', 'Undo'],
	['edit.redo', 'Edit', 'Redo'],
	['addtrack.audio', 'AddTrack', 'Audio'],
	['addtrack.marker', 'AddTrack', 'Marker'],
	['addtrack.group', 'AddTrack', 'Group Channel'],
	['addtrack.folder', 'AddTrack', 'Folder'],
	['project.remove_selected_tracks', 'Project', 'Remove Selected Tracks'],
	['project.selected_to_new_folder', 'Project', 'Folding: Tracks To Folder'],
	['project.select_track_next', 'Project', 'Select Track: Next'],
	['project.select_track_prev', 'Project', 'Select Track: Prev'],
	['transport.return_to_zero', 'Transport', 'Return to Zero'],
	['transport.locate_next_marker', 'Transport', 'Locate Next Marker'],
	['transport.locate_prev_marker', 'Transport', 'Locate Previous Marker'],
	['transport.set_left_locator', 'Transport', 'Set Left Locator'],
	['transport.set_right_locator', 'Transport', 'Set Right Locator'],
	['transport.locators_to_selection', 'Transport', 'Locators to Selection'],
	['marker.insert', 'Marker', 'Insert Marker'],
	['edit.cut', 'Edit', 'Cut'],
	['edit.copy', 'Edit', 'Copy'],
	['edit.paste', 'Edit', 'Paste'],
	['edit.delete', 'Edit', 'Delete'],
	['edit.split_at_cursor', 'Edit', 'Split at Cursor'],
	['edit.split_loop', 'Edit', 'Split Loop'],
	['edit.split_range', 'Edit', 'Split Range'],
	['edit.select_all', 'Edit', 'Select All'],
	['edit.select_none', 'Edit', 'Select None'],
	['edit.select_in_loop', 'Edit', 'Select in Loop'],
	['audio.detect_silence', 'Audio', 'Detect Silence'],
	// TW-1206: automation modes (Touch only writes while a control is touched; Auto-Latch and
	// Cross-Over start writing on any change). Behaviour in Cubase not observed yet.
	['automation.mode_touch', 'Automation', 'Automation Mode - Touch'],
	['automation.mode_auto_latch', 'Automation', 'Automation Mode - Auto-Latch'],
	['automation.mode_cross_over', 'Automation', 'Automation Mode - Cross-Over'],
	['automation.next_mode', 'Automation', 'Next Automation Mode'],
	['automation.toggle_write_selected', 'Automation', 'Toggle Write Enable Selected Tracks'],
	// Transport playback (never Record). Needed to record automation without the user pressing Play.
	['transport.start', 'Transport', 'Start'],
	['transport.stop', 'Transport', 'Stop']
]
var commands = {}
var commandErrors = []
for (var ci = 0; ci < COMMANDS.length; ci++) {
	try {
		var cv = deviceDriver.mSurface.makeCustomValueVariable('cmd_' + COMMANDS[ci][0])
		var cb = page.makeCommandBinding(cv, COMMANDS[ci][1], COMMANDS[ci][2])
		commands[COMMANDS[ci][0]] = { category: COMMANDS[ci][1], name: COMMANDS[ci][2], variable: cv, binding: cb, fired: 0 }
	} catch (e) {
		commandErrors.push({ key: COMMANDS[ci][0], err: String(e) })
	}
}
var pendingReleases = []

// ---------------------------------------------------------------- encoding helpers
function asciiEscape(str) {
	return str.replace(/[\u007f-￿]/g, function (c) {
		return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4)
	})
}

function sendPayload(activeDevice, obj) {
	var text = asciiEscape(JSON.stringify(obj))
	var count = Math.ceil(text.length / MAX_FRAGMENT_PAYLOAD)
	if (count < 1) count = 1
	if (count > MAX_FRAGMENTS) {
		text = asciiEscape(JSON.stringify({
			v: PROTOCOL_VERSION, sid: state.sessionId, rid: obj.rid || '', ok: false,
			err: { code: 'RESPONSE_TOO_LARGE', msg: 'response exceeds ' + MAX_FRAGMENTS + ' fragments; use paging' }
		}))
		count = Math.ceil(text.length / MAX_FRAGMENT_PAYLOAD)
	}
	state.seqOut = (state.seqOut + 1) % 16384
	var seq = state.seqOut
	for (var f = 0; f < count; f++) {
		var chunk = text.substr(f * MAX_FRAGMENT_PAYLOAD, MAX_FRAGMENT_PAYLOAD)
		var msg = [0xF0, MANUFACTURER, MAGIC_A, MAGIC_B, PROTOCOL_VERSION, (seq >> 7) & 0x7F, seq & 0x7F, f, count]
		for (var i = 0; i < chunk.length; i++) {
			msg.push(chunk.charCodeAt(i) & 0x7F)
		}
		msg.push(0xF7)
		midiOutput.sendMidi(activeDevice, msg)
	}
}

function reply(activeDevice, req, ok, result, errCode, errMsg, extra) {
	var resp = { v: PROTOCOL_VERSION, sid: state.sessionId, rid: req.rid, op: req.op, ok: ok }
	if (ok) {
		resp.r = result
	} else {
		resp.err = { code: errCode, msg: errMsg || '' }
	}
	if (extra) {
		for (var k in extra) {
			if (extra.hasOwnProperty(k)) resp[k] = extra[k]
		}
	}
	rememberResponse(req, resp)
	sendPayload(activeDevice, resp)
}

function rememberResponse(req, resp) {
	if (!req.rid) return
	var key = String(req.sid || '') + '/' + String(req.rid)
	if (!state.dupMap.hasOwnProperty(key)) {
		state.dupKeys.push(key)
		if (state.dupKeys.length > DUP_CACHE_SIZE) {
			var old = state.dupKeys.shift()
			delete state.dupMap[old]
		}
	}
	state.dupMap[key] = resp
	delete state.inflight[key]
}

function pushEvent(kind, objectID, tag) {
	state.eventSeq++
	state.events.push({ n: state.eventSeq, k: kind, id: objectID, t: tag === undefined ? -1 : tag, i: state.idleTicks, ms: (new Date()).getTime() })
	if (state.events.length > MAX_EVENTS) {
		state.events.shift()
		state.eventsDropped++
	}
}

// ---------------------------------------------------------------- reassembly
function onFrame(activeDevice, message) {
	var start = 0
	var end = message.length
	if (end > 0 && message[0] === 0xF0) start = 1
	if (end > 0 && message[end - 1] === 0xF7) end = end - 1
	if (end - start < HEADER_LEN - 1) { state.framesRejected++; return }
	if (message[start] !== MANUFACTURER || message[start + 1] !== MAGIC_A || message[start + 2] !== MAGIC_B) {
		state.framesRejected++
		return
	}
	var ver = message[start + 3]
	var seq = (message[start + 4] << 7) | message[start + 5]
	var idx = message[start + 6]
	var count = message[start + 7]
	if (ver !== PROTOCOL_VERSION || count < 1 || count > MAX_FRAGMENTS || idx >= count) {
		state.framesRejected++
		return
	}
	var data = ''
	for (var i = start + 8; i < end; i++) {
		var b = message[i]
		if (b > 127) { state.framesRejected++; return }
		data += String.fromCharCode(b)
	}
	if (data.length > MAX_FRAGMENT_PAYLOAD) { state.framesRejected++; return }

	var key = String(seq)
	var asm = state.assemblies[key]
	if (!asm) {
		if (state.assemblyCount >= MAX_PENDING_ASSEMBLIES) {
			state.framesRejected++
			return
		}
		asm = { count: count, parts: {}, received: 0, startedIdle: state.idleTicks }
		state.assemblies[key] = asm
		state.assemblyCount++
	}
	if (asm.count !== count) {
		delete state.assemblies[key]
		state.assemblyCount--
		state.framesRejected++
		return
	}
	if (asm.parts.hasOwnProperty(String(idx))) return // duplicate fragment: ignore
	asm.parts[String(idx)] = data
	asm.received++
	if (asm.received < asm.count) return

	var text = ''
	for (var p = 0; p < asm.count; p++) text += asm.parts[String(p)]
	delete state.assemblies[key]
	state.assemblyCount--
	handleText(activeDevice, text)
}

function expireAssemblies() {
	for (var key in state.assemblies) {
		if (state.assemblies.hasOwnProperty(key)) {
			if (state.idleTicks - state.assemblies[key].startedIdle > ASSEMBLY_MAX_IDLE_TICKS) {
				delete state.assemblies[key]
				state.assemblyCount--
				state.framesRejected++
			}
		}
	}
}

// ---------------------------------------------------------------- request dispatch
var DIRECT_OPS = { hello: true, ping: true, status: true, capabilities: true, events: true, 'transport.get': true, 'cmd.list': true, 'auto.list': true }

function handleText(activeDevice, text) {
	var req
	try {
		req = JSON.parse(text)
	} catch (e) {
		state.lastError = 'bad json'
		sendPayload(activeDevice, { v: PROTOCOL_VERSION, sid: state.sessionId, rid: '', ok: false, err: { code: 'BAD_REQUEST', msg: 'invalid JSON' } })
		return
	}
	if (typeof req !== 'object' || req === null || typeof req.op !== 'string' || typeof req.rid !== 'string') {
		sendPayload(activeDevice, { v: PROTOCOL_VERSION, sid: state.sessionId, rid: '', ok: false, err: { code: 'BAD_REQUEST', msg: 'missing op/rid' } })
		return
	}
	if (req.v !== PROTOCOL_VERSION) {
		reply(activeDevice, req, false, null, 'PROTOCOL_MISMATCH', 'script speaks v' + PROTOCOL_VERSION)
		return
	}
	panelActivity(activeDevice)
	var dupKey = String(req.sid || '') + '/' + req.rid
	if (state.dupMap.hasOwnProperty(dupKey)) {
		var cached = state.dupMap[dupKey]
		var copy = {}
		for (var k in cached) if (cached.hasOwnProperty(k)) copy[k] = cached[k]
		copy.dup = true
		sendPayload(activeDevice, copy)
		return
	}
	// Verified on Cubase Elements 15 (script 0.1.2): a duplicate arriving while the original is still
	// queued for idle was executed twice. Drop it silently: the original's response will answer the rid.
	if (state.inflight.hasOwnProperty(dupKey)) {
		state.dupInFlightDropped++
		return
	}
	if (req.op !== 'hello' && req.op !== 'ping' && req.sid !== state.sessionId) {
		reply(activeDevice, req, false, null, 'STALE_SESSION', 'expected session ' + state.sessionId)
		return
	}
	if (DIRECT_OPS[req.op]) {
		try {
			reply(activeDevice, req, true, runDirect(req), null, null, { via: 'sysex' })
		} catch (e) {
			reply(activeDevice, req, false, null, 'SCRIPT_ERROR', String(e), { via: 'sysex' })
		}
		return
	}
	if (!IDLE_OPS[req.op]) {
		reply(activeDevice, req, false, null, 'UNKNOWN_OP', req.op)
		return
	}
	if (state.queue.length >= MAX_QUEUE) {
		reply(activeDevice, req, false, null, 'BUSY', 'queue full')
		return
	}
	if (req.rid) state.inflight[dupKey] = true
	state.queue.push({ req: req, queuedAtIdle: state.idleTicks })
}

function capabilities() {
	var c = {
		json: hasJSON,
		makeDirectAccess: !!page.mHostAccess.makeDirectAccess,
		directAccessCreated: !!daSel,
		directAccessError: daError,
		mixerDirectAccessCreated: !!daMix,
		mixerDirectAccessError: daMixError,
		mixerDirectAccessActive: !!state.daMixActive,
		transportTimeDisplay: !!timeDisplay,
		commandsBound: (function () { var n = 0; for (var k in commands) if (commands.hasOwnProperty(k)) n++; return n })(),
		commandErrors: commandErrors.length,
		writePolicy: 'open',
		panel: panel ? { enabled: true, errors: panel.errors.slice(-10) } : { enabled: false },
		automationControls: autoControls ? { enabled: true, count: autoControls.list.length, errors: autoControls.errors.slice(-10) } : { enabled: false },
		pageMOnIdle: true,
		methods: {}
	}
	if (daSel) {
		var da = daSel
		var names = ['activate', 'deactivate', 'update', 'getBaseObjectID', 'getNumberOfChildObjects', 'getChildObjectID',
			'getObjectUniqueName', 'getObjectTypeName', 'getObjectUniqueIDString', 'getObjectTitle', 'getNumberOfParameters',
			'getParameterTagByIndex', 'getParameterTitle', 'getParameterProcessValue', 'setParameterProcessValue',
			'getParameterDisplayValue', 'getParameterDisplayUnits', 'getParameterProcessValueType', 'isParameterAutomatable',
			'convertParameterProcessValueToPlain', 'convertParameterPlainToProcessValue', 'getParameterEditLockState',
			'getParameterDefaultProcessValue', 'getMixerChannelIndex', 'getMixerChannelZone', 'isMixerChannelVisible',
			'setParameterDisplayValue']
		for (var i = 0; i < names.length; i++) c.methods[names[i]] = typeof da[names[i]] === 'function'
		var pm = da.mPluginManager
		c.pluginManager = !!pm
		if (pm) {
			var pmNames = ['getNumberOfPluginCollections', 'getPluginCollectionByIndex', 'getIndexOfDefaultPluginCollection',
				'getIndexOfActivePluginCollection', 'trySetSlotPlugin', 'resetSlotPlugin']
			for (var j = 0; j < pmNames.length; j++) c.methods['pm.' + pmNames[j]] = typeof pm[pmNames[j]] === 'function'
		}
	}
	return c
}

function hostInfo() {
	var info = { appName: null, appVersion: null, insertSlots: null }
	try {
		var d = midiremote_api.mDefaults
		if (d) {
			if (typeof d.getAppName === 'function') info.appName = d.getAppName()
			if (d.mAppVersion && typeof d.mAppVersion.getVersionString === 'function') info.appVersion = d.mAppVersion.getVersionString()
			if (typeof d.getNumberOfInsertEffectSlots === 'function') info.insertSlots = d.getNumberOfInsertEffectSlots()
		}
	} catch (e) {
		info.error = String(e)
	}
	return info
}

function runDirect(req) {
	if (req.op === 'ping') {
		return { pong: true, scriptVersion: SCRIPT_VERSION, protocol: PROTOCOL_VERSION, echo: req.p ? req.p.echo : null }
	}
	if (req.op === 'hello') {
		return { scriptVersion: SCRIPT_VERSION, protocol: PROTOCOL_VERSION, sessionId: state.sessionId, loadedAt: state.loadedAt, host: hostInfo() }
	}
	if (req.op === 'status') {
		return {
			deviceActive: state.deviceActive, pageActive: state.pageActive, daActive: state.daActive,
			idleTicks: state.idleTicks, deviceIdleTicks: state.deviceIdleTicks, sysexIn: state.sysexIn,
			framesRejected: state.framesRejected, daMixActive: state.daMixActive, queue: state.queue.length, dupInFlightDropped: state.dupInFlightDropped, pendingAssemblies: state.assemblyCount,
			lastError: state.lastError, removedObjects: state.removedObjects, changedObjects: state.changedObjects,
			changedParameters: state.changedParameters
		}
	}
	if (req.op === 'capabilities') {
		return { capabilities: capabilities(), host: hostInfo() }
	}
	if (req.op === 'transport.get') {
		return { available: !!timeDisplay, primary: transport.primary, secondary: transport.secondary, tempoBPM: transport.tempoBPM, updates: transport.updates }
	}
	if (req.op === 'auto.list') {
		if (!autoControls) return { enabled: false, controls: [] }
		var controls = []
		for (var i = 0; i < autoControls.list.length; i++) controls.push(describeControl(autoControls.list[i]))
		return { enabled: true, controls: controls, errors: autoControls.errors.slice(-10) }
	}
	if (req.op === 'cmd.list') {
		var list = []
		for (var k in commands) if (commands.hasOwnProperty(k)) list.push({ key: k, category: commands[k].category, name: commands[k].name, fired: commands[k].fired })
		return { commands: list, errors: commandErrors }
	}
	if (req.op === 'events') {
		var ev = state.events
		var dropped = state.eventsDropped
		state.events = []
		state.eventsDropped = 0
		return { events: ev, dropped: dropped, lastSeq: state.eventSeq, idleTicks: state.idleTicks, ms: (new Date()).getTime() }
	}
	throw new Error('unreachable')
}

// ---------------------------------------------------------------- DirectAccess ops (idle context)
function num(p, name, def) {
	var v = p && p[name]
	if (v === undefined || v === null) {
		if (def !== undefined) return def
		throw { code: 'BAD_REQUEST', msg: 'missing ' + name }
	}
	if (typeof v !== 'number' || v !== v) throw { code: 'BAD_REQUEST', msg: name + ' must be a number' }
	return v
}

function clampLimit(v, max) {
	if (v < 1) return 1
	if (v > max) return max
	return Math.floor(v)
}

function describeObject(am, id) {
	var o = { id: id }
	try { o.title = da.getObjectTitle(am, id) } catch (e1) { o.title = null }
	try { o.type = da.getObjectTypeName(am, id) } catch (e2) { o.type = null }
	try { o.uniqueName = da.getObjectUniqueName(am, id) } catch (e3) { o.uniqueName = null }
	try { o.uid = da.getObjectUniqueIDString(am, id) } catch (e4) { o.uid = null }
	try { o.children = da.getNumberOfChildObjects(am, id) } catch (e5) { o.children = null }
	try { o.params = da.getNumberOfParameters(am, id) } catch (e6) { o.params = null }
	return o
}

function describeParam(am, id, tag) {
	var p = { tag: tag }
	try { p.title = da.getParameterTitle(am, id, tag, 128) } catch (e1) { p.title = null }
	try { p.process = da.getParameterProcessValue(am, id, tag) } catch (e2) { p.process = null }
	try { p.display = da.getParameterDisplayValue(am, id, tag) } catch (e3) { p.display = null }
	try { p.units = da.getParameterDisplayUnits(am, id, tag) } catch (e4) { p.units = null }
	try { p.valueType = da.getParameterProcessValueType(am, id, tag) } catch (e5) { p.valueType = null }
	try { p.automatable = da.isParameterAutomatable(am, id, tag) } catch (e6) { p.automatable = null }
	try { p.editLock = da.getParameterEditLockState(am, id, tag) } catch (e7) { p.editLock = null }
	try { p.defaultProcess = da.getParameterDefaultProcessValue(am, id, tag) } catch (e8) { p.defaultProcess = null }
	if (typeof p.process === 'number') {
		try { p.plain = da.convertParameterProcessValueToPlain(am, id, tag, p.process) } catch (e9) { p.plain = null }
	}
	return p
}

// Verified on Cubase Elements 15.0.30: querying a removed object does not throw; it returns
// sentinels (title "", children -1, params -1, process -1). Treat children === -1 as invalid.
function assertValid(am, id) {
	var n = da.getNumberOfChildObjects(am, id)
	if (n === -1) throw { code: 'INVALID_OBJECT', msg: 'object ' + id + ' is not valid (removed or unknown)' }
	return n
}

// Write context (0.2.0): no title restriction any more. Records the base object and, when the caller
// sends expectChannelTitle, checks it (a precondition chosen by the caller, not a global restriction).
// The subtree path is reported when the target is under the base; a target elsewhere is allowed.
function guardTarget(am, targetId, p) {
	var base = da.getBaseObjectID(am)
	var title = base >= 0 ? da.getObjectTitle(am, base) : null
	if (p && typeof p.expectChannelTitle === 'string' && title !== p.expectChannelTitle) {
		throw { code: 'PRECONDITION_FAILED', msg: 'base channel title is "' + title + '", expected "' + p.expectChannelTitle + '"' }
	}
	if (base < 0) return { base: base, baseTitle: null, path: null, policy: 'open' }
	if (targetId === base) return { base: base, baseTitle: title, path: [base], policy: 'open' }
	var stack = [{ id: base, depth: 0, path: [base] }]
	var visited = 0
	while (stack.length > 0) {
		var cur = stack.pop()
		visited++
		if (visited > GUARD_MAX_NODES) break
		if (cur.depth >= GUARD_MAX_DEPTH) continue
		var n = da.getNumberOfChildObjects(am, cur.id)
		for (var i = 0; i < n; i++) {
			var c = da.getChildObjectID(am, cur.id, i)
			var path = cur.path.concat([c])
			if (c === targetId) return { base: base, baseTitle: title, path: path, policy: 'open' }
			stack.push({ id: c, depth: cur.depth + 1, path: path })
		}
	}
	return { base: base, baseTitle: title, path: null, policy: 'open', outsideBase: true }
}

var NO_DA_OPS = { 'auto.control': true, 'sel.step': true, 'transport.setTime': true, 'transport.setTempo': true, 'cmd.canPerform': true, 'cmd.run': true }

var IDLE_OPS = {
	'da.base': function (am, p) {
		var base = da.getBaseObjectID(am)
		if (base < 0) return { base: base }
		return { base: base, object: describeObject(am, base) }
	},
	'da.object': function (am, p) {
		var oid = num(p, 'id')
		assertValid(am, oid)
		return describeObject(am, oid)
	},
	'da.children': function (am, p) {
		var id = num(p, 'id')
		var offset = Math.max(0, Math.floor(num(p, 'offset', 0)))
		var limit = clampLimit(num(p, 'limit', 20), 50)
		var total = assertValid(am, id)
		var items = []
		for (var i = offset; i < total && items.length < limit; i++) {
			var cid = da.getChildObjectID(am, id, i)
			var d = describeObject(am, cid)
			d.index = i
			items.push(d)
		}
		return { id: id, total: total, offset: offset, items: items }
	},
	'da.params': function (am, p) {
		var id = num(p, 'id')
		var offset = Math.max(0, Math.floor(num(p, 'offset', 0)))
		var limit = clampLimit(num(p, 'limit', 10), 25)
		assertValid(am, id)
		var total = da.getNumberOfParameters(am, id)
		var items = []
		for (var i = offset; i < total && items.length < limit; i++) {
			var tag = da.getParameterTagByIndex(am, id, i)
			var d = describeParam(am, id, tag)
			d.index = i
			items.push(d)
		}
		return { id: id, total: total, offset: offset, items: items }
	},
	'da.param.get': function (am, p) {
		var pid = num(p, 'id')
		assertValid(am, pid)
		return describeParam(am, pid, num(p, 'tag'))
	},
	'da.convert': function (am, p) {
		var id = num(p, 'id')
		var tag = num(p, 'tag')
		assertValid(am, id)
		var out = { id: id, tag: tag }
		if (p.process !== undefined) out.plainFromProcess = da.convertParameterProcessValueToPlain(am, id, tag, num(p, 'process'))
		if (p.plain !== undefined) out.processFromPlain = da.convertParameterPlainToProcessValue(am, id, tag, num(p, 'plain'))
		return out
	},
	'da.param.set': function (am, p) {
		var id = num(p, 'id')
		var tag = num(p, 'tag')
		var value = num(p, 'value')
		assertValid(am, id)
		var guard = guardTarget(am, id, p)
		var before = describeParam(am, id, tag)
		// Verified (POC): the host clamps process writes to [0,1]. Discrete values read outside that
		// range (routing: 'Stereo Out' = 22) cannot be written back, so they are refused here.
		if (value < 0 || value > 1) throw { code: 'BAD_REQUEST', msg: 'process value must be in [0,1]' }
		if (typeof p.expectTitle === 'string' && before.title !== p.expectTitle) {
			throw { code: 'PRECONDITION_FAILED', msg: 'parameter title is "' + before.title + '", expected "' + p.expectTitle + '"' }
		}
		if (before.editLock === true) throw { code: 'PRECONDITION_FAILED', msg: 'parameter is edit-locked' }
		da.setParameterProcessValue(am, id, tag, value)
		var after = describeParam(am, id, tag)
		return { guard: guard, before: before, after: after, requested: value }
	},
	'da.param.setDisplay': function (am, p) {
		var id = num(p, 'id')
		var tag = num(p, 'tag')
		if (typeof p.value !== 'string') throw { code: 'BAD_REQUEST', msg: 'value must be a string' }
		assertValid(am, id)
		var guard = guardTarget(am, id, p)
		var before = describeParam(am, id, tag)
		if (typeof p.expectTitle === 'string' && before.title !== p.expectTitle) {
			throw { code: 'PRECONDITION_FAILED', msg: 'parameter title is "' + before.title + '", expected "' + p.expectTitle + '"' }
		}
		if (before.editLock === true) throw { code: 'PRECONDITION_FAILED', msg: 'parameter is edit-locked' }
		da.setParameterDisplayValue(am, id, tag, p.value)
		var after = describeParam(am, id, tag)
		return { guard: guard, before: before, after: after, requested: p.value }
	},
	// Batched mixer listing (one idle tick): children of the base with metadata, mixer position and
	// a few channel parameters by tag (defaults: name, selected, volume, mute, solo, input, output).
	'da.channels': function (am, p) {
		var base = da.getBaseObjectID(am)
		if (base < 0) return { base: base, total: 0, items: [] }
		var offset = Math.max(0, Math.floor(num(p, 'offset', 0)))
		var limit = clampLimit(num(p, 'limit', 16), 32)
		var tags = (p.tags && p.tags.length) ? p.tags : [1024, 4000, 1025, 1027, 1028, 4101, 4102]
		var total = assertValid(am, base)
		var items = []
		var seen = {}
		var duplicates = []
		for (var i = offset; i < total && items.length < limit; i++) {
			var cid = da.getChildObjectID(am, base, i)
			// Verified (0.2.0): the last child of 'VST Mixer' repeats the last channel with the same ID.
			if (seen[cid]) { duplicates.push({ index: i, id: cid }); continue }
			seen[cid] = true
			var d = describeObject(am, cid)
			d.index = i
			try { d.mixerVisible = da.isMixerChannelVisible(am, cid) } catch (e1) { d.mixerVisible = null }
			try { d.mixerIndex = da.getMixerChannelIndex(am, cid) } catch (e2) { d.mixerIndex = null }
			try { d.mixerZone = da.getMixerChannelZone(am, cid) } catch (e3) { d.mixerZone = null }
			d.values = {}
			for (var t = 0; t < tags.length; t++) {
				var tg = tags[t]
				try {
					d.values[String(tg)] = { title: da.getParameterTitle(am, cid, tg, 64), display: da.getParameterDisplayValue(am, cid, tg), process: da.getParameterProcessValue(am, cid, tg) }
				} catch (e4) { d.values[String(tg)] = null }
			}
			items.push(d)
		}
		return { base: base, baseObject: describeObject(am, base), total: total, offset: offset, items: items, duplicates: duplicates }
	},
	'transport.setTempo': function (am, p) {
		if (!timeDisplay) throw { code: 'UNSUPPORTED', msg: 'mTimeDisplay not available' }
		var bpm = num(p, 'bpm')
		if (bpm < 20 || bpm > 300) throw { code: 'BAD_REQUEST', msg: 'bpm must be in [20,300]' }
		var before = transport.tempoBPM
		timeDisplay.setTempoBPM(am, bpm)
		return { requested: bpm, before: before }
	},
	// TW-1206/1207: touch / move / release one automation control (bound to a parameter of the selected track).
	'auto.control': function (am, p, activeDevice) {
		if (!autoControls) throw { code: 'UNSUPPORTED', msg: 'automation controls are not enabled in this script build' }
		var c = autoControls.byKey[p.key]
		if (!c) throw { code: 'NOT_FOUND', msg: 'unknown automation control ' + p.key }
		var touchedBefore = c.touched
		if (p.touch === true && !c.touched) {
			c.touch.setProcessValue(activeDevice, 1)
			c.touched = true
		}
		if (p.value !== undefined) {
			var value = num(p, 'value')
			if (value < 0 || value > 1) throw { code: 'BAD_REQUEST', msg: 'value must be in [0,1]' }
			c.fader.mSurfaceValue.setProcessValue(activeDevice, value)
			c.value = c.fader.mSurfaceValue.getProcessValue(activeDevice)
		}
		if (p.touch === false && c.touched) {
			c.touch.setProcessValue(activeDevice, 0)
			c.touched = false
		}
		var out = describeControl(c)
		out.touchedBefore = touchedBefore
		return out
	},
	'sel.step': function (am, p) {
		var dir = p.direction
		var act = page.mHostAccess.mTrackSelection.mAction
		if (dir === 'next') act.mNextTrack.trigger(am)
		else if (dir === 'prev') act.mPrevTrack.trigger(am)
		else throw { code: 'BAD_REQUEST', msg: 'direction must be next|prev' }
		return { triggered: dir }
	},
	'transport.setTime': function (am, p) {
		if (!timeDisplay) throw { code: 'UNSUPPORTED', msg: 'mTimeDisplay not available' }
		var which = p.which || 'locator'
		var disp = p.display || 'secondary'
		if (!TIME_FIELDS.hasOwnProperty(which)) throw { code: 'BAD_REQUEST', msg: 'which must be locator|cycleLeft|cycleRight' }
		if (disp !== 'primary' && disp !== 'secondary') throw { code: 'BAD_REQUEST', msg: 'display must be primary|secondary' }
		if (typeof p.time !== 'string' || p.time.length === 0 || p.time.length > 32) throw { code: 'BAD_REQUEST', msg: 'time must be a non-empty string' }
		var before = transport[disp][which]
		timeDisplay[disp === 'primary' ? 'mPrimary' : 'mSecondary'][TIME_FIELDS[which]].setTime(am, p.time)
		// The new value arrives later through mOnChange: read it back with transport.get.
		return { which: which, display: disp, requested: p.time, before: before }
	},
	'cmd.canPerform': function (am, p) {
		var out = {}
		for (var k in commands) {
			if (!commands.hasOwnProperty(k)) continue
			if (p.key && p.key !== k) continue
			try { out[k] = commands[k].binding.canPerform(am) } catch (e) { out[k] = 'error: ' + String(e) }
		}
		return { canPerform: out }
	},
	'cmd.run': function (am, p, activeDevice) {
		var c = commands[p.key]
		if (!c) throw { code: 'NOT_FOUND', msg: 'unknown command key ' + p.key }
		var can = null
		try { can = c.binding.canPerform(am) } catch (e) { can = 'error: ' + String(e) }
		if (can === false && p.force !== true) throw { code: 'CANNOT_PERFORM', msg: 'canPerform=false for ' + c.category + '/' + c.name }
		c.variable.setProcessValue(activeDevice, 1)
		c.fired++
		pendingReleases.push({ variable: c.variable, atTick: state.idleTicks + 1 })
		return { key: p.key, category: c.category, name: c.name, canPerform: can, fired: c.fired }
	},
	'pm.collections': function (am, p) {
		var slot = num(p, 'slot')
		var pm = da.mPluginManager
		if (!pm) throw { code: 'UNSUPPORTED', msg: 'mPluginManager not available' }
		assertValid(am, slot)
		var n = pm.getNumberOfPluginCollections(am, slot)
		var items = []
		for (var i = 0; i < n && i < 50; i++) {
			var c = pm.getPluginCollectionByIndex(am, slot, i)
			items.push({ index: i, name: c ? c.mName : null, entries: (c && c.mEntries) ? c.mEntries.length : null })
		}
		return {
			slot: slot, total: n, items: items,
			defaultIndex: pm.getIndexOfDefaultPluginCollection(am, slot),
			activeIndex: pm.getIndexOfActivePluginCollection(am, slot)
		}
	},
	'pm.entries': function (am, p) {
		var slot = num(p, 'slot')
		var ci = num(p, 'collection')
		var offset = Math.max(0, Math.floor(num(p, 'offset', 0)))
		var limit = clampLimit(num(p, 'limit', 20), 40)
		var filter = typeof p.filter === 'string' ? p.filter.toLowerCase() : ''
		var pm = da.mPluginManager
		if (!pm) throw { code: 'UNSUPPORTED', msg: 'mPluginManager not available' }
		assertValid(am, slot)
		var c = pm.getPluginCollectionByIndex(am, slot, ci)
		if (!c || !c.mEntries) throw { code: 'NOT_FOUND', msg: 'collection ' + ci }
		var items = []
		var matched = 0
		for (var i = 0; i < c.mEntries.length; i++) {
			var e = c.mEntries[i]
			var name = String(e.mPluginName)
			var vendor = String(e.mPluginVendor)
			if (filter && (name + ' ' + vendor + ' ' + String(e.mSubCategories)).toLowerCase().indexOf(filter) < 0) continue
			if (matched >= offset && items.length < limit) {
				items.push({
					index: i, name: name, vendor: vendor, version: String(e.mPluginVersion), format: String(e.mFormatVersion),
					subCategories: String(e.mSubCategories), uid: String(e.mPluginUID), path: String(e.mCollectionPath)
				})
			}
			matched++
		}
		return { slot: slot, collection: ci, collectionName: c.mName, total: c.mEntries.length, matched: matched, offset: offset, items: items }
	},
	'pm.set': function (am, p) {
		var slot = num(p, 'slot')
		var uid = p.uid
		if (typeof uid !== 'string' || uid.length === 0) throw { code: 'BAD_REQUEST', msg: 'uid required' }
		var pm = da.mPluginManager
		if (!pm) throw { code: 'UNSUPPORTED', msg: 'mPluginManager not available' }
		assertValid(am, slot)
		var guard = guardTarget(am, slot, p)
		var before = describeObject(am, slot)
		// Verified on Cubase Elements 15.0.30: an empty insert slot has children=0 and 8 slot-level
		// parameters (on, edit, bypass, effect type...). A loaded plugin appears as a child object.
		if (before.type !== 'Slot') {
			throw { code: 'PRECONDITION_FAILED', msg: 'target is not a Slot (type=' + before.type + ')' }
		}
		if (before.children !== 0) {
			throw { code: 'SLOT_NOT_EMPTY', msg: 'slot has ' + before.children + ' child object(s)' }
		}
		var ok = pm.trySetSlotPlugin(am, slot, uid, p.dontAskDiscard === true)
		var after = describeObject(am, slot)
		return { guard: guard, result: ok, before: before, after: after }
	}
}

function runQueued(activeDevice, activeMapping) {
	var n = 0
	while (state.queue.length > 0 && n < MAX_OPS_PER_IDLE) {
		var item = state.queue.shift()
		n++
		var req = item.req
		var extra = { via: 'idle', waitTicks: state.idleTicks - item.queuedAtIdle }
		var scope = (req.p && req.p.scope) || 'selected'
		da = scope === 'mixer' ? daMix : daSel
		extra.scope = scope
		if (NO_DA_OPS[req.op]) {
			try {
				reply(activeDevice, req, true, IDLE_OPS[req.op](activeMapping, req.p || {}, activeDevice), null, null, extra)
			} catch (eN) {
				reply(activeDevice, req, false, null, (eN && eN.code) ? eN.code : 'SCRIPT_ERROR', (eN && eN.msg) ? eN.msg : String(eN), extra)
			}
			continue
		}
		if (!da) {
			reply(activeDevice, req, false, null, 'UNSUPPORTED', 'DirectAccess (' + scope + ') unavailable: ' + (scope === 'mixer' ? daMixError : daError), extra)
			continue
		}
		if (!state.daActive) {
			reply(activeDevice, req, false, null, 'NOT_ACTIVE', 'DirectAccess not activated', extra)
			continue
		}
		try {
			var result = IDLE_OPS[req.op](activeMapping, req.p || {}, activeDevice)
			reply(activeDevice, req, true, result, null, null, extra)
		} catch (e) {
			var code = (e && e.code) ? e.code : 'SCRIPT_ERROR'
			var msg = (e && e.msg) ? e.msg : String(e)
			reply(activeDevice, req, false, null, code, msg, extra)
		}
	}
}

// ---------------------------------------------------------------- host callbacks
midiInput.mOnSysex = function (activeDevice, message) {
	state.sysexIn++
	try {
		onFrame(activeDevice, message)
	} catch (e) {
		state.lastError = 'onFrame: ' + String(e)
	}
}

deviceDriver.mOnActivate = function (activeDevice) {
	state.deviceActive = true
	console.log('Trackwright bridge ' + SCRIPT_VERSION + ' activated, session ' + state.sessionId + ', json=' + hasJSON)
}

deviceDriver.mOnDeactivate = function (activeDevice) {
	state.deviceActive = false
}

deviceDriver.mOnIdle = function (activeDevice) {
	state.deviceIdleTicks++
}

page.mOnActivate = function (activeDevice, activeMapping) {
	state.pageActive = true
	if (daSel) {
		try {
			daSel.activate(activeMapping)
			state.daActive = true
		} catch (e) {
			daError = 'activate threw: ' + String(e)
		}
	}
	if (daMix) {
		try {
			daMix.activate(activeMapping)
			state.daMixActive = true
		} catch (e2) {
			daMixError = 'activate threw: ' + String(e2)
		}
	}
}

page.mOnDeactivate = function (activeDevice, activeMapping) {
	state.pageActive = false
	if (daSel && state.daActive) {
		try { daSel.deactivate(activeMapping) } catch (e) { }
	}
	if (daMix && state.daMixActive) {
		try { daMix.deactivate(activeMapping) } catch (e2) { }
	}
	state.daActive = false
	state.daMixActive = false
	state.queue = []
	state.inflight = {}
}

page.mOnIdle = function (activeDevice, activeMapping) {
	state.idleTicks++
	expireAssemblies()
	panelIdle(activeDevice)
	if (pendingReleases.length > 0) {
		var keep = []
		for (var r = 0; r < pendingReleases.length; r++) {
			if (state.idleTicks >= pendingReleases[r].atTick) {
				try { pendingReleases[r].variable.setProcessValue(activeDevice, 0) } catch (e) { state.lastError = 'release: ' + String(e) }
			} else keep.push(pendingReleases[r])
		}
		pendingReleases = keep
	}
	if (state.queue.length > 0) runQueued(activeDevice, activeMapping)
}

if (daMix) {
	daMix.mOnObjectWillBeRemoved = function (activeDevice, activeMapping, objectID) {
		state.removedObjects++
		pushEvent('mix.removed', objectID)
	}
}

if (daSel) {
	daSel.mOnObjectWillBeRemoved = function (activeDevice, activeMapping, objectID) {
		state.removedObjects++
		pushEvent('removed', objectID)
	}
	daSel.mOnObjectChange = function (activeDevice, activeMapping, objectID) {
		state.changedObjects++
		pushEvent('changed', objectID)
	}
	daSel.mOnParameterChange = function (activeDevice, activeMapping, objectID, parameterTag) {
		state.changedParameters++
		pushEvent('param', objectID, parameterTag)
	}
}
