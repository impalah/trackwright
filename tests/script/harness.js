// Node.js harness that runs the real Trackwright MIDI Remote script without Cubase.
//
// It emulates the subset of the MIDI Remote API the script uses, with an in-memory mixer that
// reproduces behaviours verified in the POC (duplicated last mixer child, sentinels for removed
// objects, writes clamped to [0,1], single selection, command bindings with canPerform).
//
// Usage: node harness.js <script.js>
// Protocol: one JSON step per stdin line, one JSON reply per stdout line. A step may contain
//   "frames": [[...sysex data...], ...]   deliver frames to the script's MIDI input
//   "idle": n                             run n page idle ticks
//   "remove": objectId                    remove an object (as if deleted in Cubase)
//   "state": true                         include harness state (fired commands, selection, ids)
// Reply: {"sent": [frames sent by the script during the step], "logs": [...], "state"?: {...}}
'use strict'

var Module = require('module')
var path = require('path')

// ------------------------------------------------------------------ in-memory host model
var nextId = 10
var objects = {}
function obj(type, title, extra) {
	var id = nextId++
	objects[id] = Object.assign({ id: id, type: type, title: title, uniqueName: type, uid: 'UID' + id, children: [], params: {}, removed: false }, extra || {})
	return objects[id]
}
function param(o, tag, title, kind, value, display) {
	o.params[tag] = { title: title, kind: kind, value: value, text: display }
}
function channel(type, title) {
	var ch = obj(type, title)
	param(ch, 1024, 'Nombre', 'text', 1, title)
	param(ch, 4000, 'Seleccionado', 'discrete', 0)
	param(ch, 1025, 'Volumen', 'continuous', 0.7890865802764893)
	param(ch, 1027, 'Enmudecer', 'discrete', 0)
	param(ch, 1028, 'Solo', 'discrete', 0)
	param(ch, 4102, 'Salida', 'discrete', 22, 'Stereo Out')
	var inserts = obj('Inserts', 'Inserciones')
	for (var i = 1; i <= 8; i++) {
		var slot = obj('Slot', String(i))
		param(slot, 4125, 'Tipo de efecto', 'discrete', 0, 'Ningún efecto')
		inserts.children.push(slot.id)
	}
	ch.children.push(inserts.id)
	var strips = obj('Strips', 'Strip')
	var eqSlot = obj('Slot', '3')
	var eq = obj('EQ', 'EQ')
	param(eq, 4232, 'EQ 1 Gain', 'continuous', 0.5)
	eqSlot.children.push(eq.id)
	strips.children.push(eqSlot.id)
	ch.children.push(strips.id)
	return ch
}
var mixer = obj('VST Mixer', 'VST Mixer')
var out = channel('OutputChannel', 'Stereo Out')
var instr = channel('Synth', 'POC-INSTR')
var audio = channel('AudioChannel', 'POC-TEST')
mixer.children = [out.id, instr.id, audio.id, audio.id] // verified quirk: last child duplicated
var selectedId = audio.id
audio.params[4000].value = 1

var PLUGINS = [
	{ mPluginName: 'StudioEQ', mPluginVendor: 'Steinberg Media Technologies', mPluginVersion: '1.0', mFormatVersion: 'VST3', mSubCategories: 'Fx|EQ', mPluginUID: '946051208E29496E804F64A825C8A047', mCollectionPath: '' },
	{ mPluginName: 'Compressor', mPluginVendor: 'Steinberg Media Technologies', mPluginVersion: '1.0', mFormatVersion: 'VST3', mSubCategories: 'Fx|Dynamics', mPluginUID: '5B38F28281144FFE80285FF7CCF20483', mCollectionPath: '' }
]

function live(id) {
	var o = objects[id]
	return o && !o.removed ? o : null
}
function displayOf(p) {
	if (p.kind === 'text') return p.text
	if (p.text !== undefined && p.kind === 'discrete' && p.value > 1) return p.text
	if (p.kind === 'discrete') return p.value >= 0.5 ? 'Activ.' : 'Desact.'
	return p.value.toFixed(2)
}

var logs = []
var fired = []
var surfaceElements = []
var panelLog = []
var listeners = { remove: [], change: [], param: [] }

function makeDirectAccess(hostObject) {
	var da = {
		mPluginManager: null,
		activate: function () {},
		deactivate: function () {},
		update: function () {},
		getBaseObjectID: function () { return hostObject === 'mixer' ? mixer.id : selectedId },
		getNumberOfChildObjects: function (am, id) { var o = live(id); return o ? o.children.length : -1 },
		getChildObjectID: function (am, id, i) { return live(id).children[i] },
		getObjectTitle: function (am, id) { var o = live(id); return o ? o.title : '' },
		getObjectTypeName: function (am, id) { var o = live(id); return o ? o.type : '' },
		getObjectUniqueName: function (am, id) { var o = live(id); return o ? o.uniqueName : '' },
		getObjectUniqueIDString: function (am, id) { var o = live(id); return o ? o.uid : '' },
		getNumberOfParameters: function (am, id) { var o = live(id); return o ? Object.keys(o.params).length : -1 },
		getParameterTagByIndex: function (am, id, i) { return Number(Object.keys(live(id).params)[i]) },
		getParameterTitle: function (am, id, tag) { var o = live(id); return o && o.params[tag] ? o.params[tag].title : '' },
		getParameterProcessValue: function (am, id, tag) { var o = live(id); return o && o.params[tag] ? o.params[tag].value : -1 },
		setParameterProcessValue: function (am, id, tag, v) {
			var o = live(id)
			if (!o || !o.params[tag]) return
			v = Math.max(0, Math.min(1, v)) // verified: the host clamps to [0,1]
			o.params[tag].value = v
			if (tag === 4000 && v >= 0.5) {
				Object.keys(objects).forEach(function (k) { if (objects[k].params[4000]) objects[k].params[4000].value = 0 })
				o.params[4000].value = 1
				selectedId = id
			}
			if (tag === 4102) o.params[tag].text = 'Sin bus'
		},
		getParameterDisplayValue: function (am, id, tag) { var o = live(id); return o && o.params[tag] ? displayOf(o.params[tag]) : '' },
		setParameterDisplayValue: function (am, id, tag, text) {
			var o = live(id)
			if (o && o.params[tag] && o.params[tag].kind === 'text') {
				o.params[tag].text = text
				if (tag === 1024) o.title = text
			}
		},
		getParameterDisplayUnits: function () { return '' },
		getParameterProcessValueType: function (am, id, tag) { return live(id).params[tag].kind },
		isParameterAutomatable: function (am, id, tag) { return tag === 1025 || tag === 1027 },
		getParameterEditLockState: function () { return false },
		getParameterDefaultProcessValue: function () { return -1 },
		convertParameterProcessValueToPlain: function (am, id, tag, v) { return v * 48 - 24 },
		convertParameterPlainToProcessValue: function (am, id, tag, v) { return (v + 24) / 48 },
		isMixerChannelVisible: function () { return true },
		getMixerChannelIndex: function (am, id) { return mixer.children.indexOf(id) },
		getMixerChannelZone: function () { return 0 }
	}
	da.mPluginManager = {
		getNumberOfPluginCollections: function (am, slot) { var o = live(slot); return o && o.type === 'Slot' ? 1 : 0 },
		getPluginCollectionByIndex: function () { return { mName: 'Por defecto', mEntries: PLUGINS } },
		getIndexOfDefaultPluginCollection: function () { return 0 },
		getIndexOfActivePluginCollection: function () { return 0 },
		trySetSlotPlugin: function (am, slot, uid) {
			var entry = PLUGINS.filter(function (e) { return e.mPluginUID === uid })[0]
			if (!entry) return false
			var plugin = obj('Plugin', entry.mPluginName, { uniqueName: uid + '-0' })
			param(plugin, 4207, 'GainP1L', 'continuous', 0.5)
			live(slot).children.push(plugin.id)
			return true
		},
		resetSlotPlugin: function () { return false }
	}
	listeners.da = listeners.da || []
	listeners.da.push(da)
	return da
}

// ------------------------------------------------------------------ MIDI Remote API surface
var sent = []
var midiInput = null
var page = null
var device = { name: 'activeDevice' }
var mapping = { name: 'activeMapping' }

function timeField(display, name) {
	return {
		mOnChange: null,
		_time: '1. 1. 1.  0',
		setTime: function (am, t) {
			this._time = t
			if (this.mOnChange) this.mOnChange(device, mapping, t, display === 'primary' ? 'Compases+Tiempos' : 'Segundos')
		}
	}
}
var timeDisplay = {
	mPrimary: { mTransportLocator: timeField('primary'), mCycleLocatorLeft: timeField('primary'), mCycleLocatorRight: timeField('primary') },
	mSecondary: { mTransportLocator: timeField('secondary'), mCycleLocatorLeft: timeField('secondary'), mCycleLocatorRight: timeField('secondary') },
	mOnChangeTempoBPM: null,
	setTempoBPM: function (am, bpm) { if (this.mOnChangeTempoBPM) this.mOnChangeTempoBPM(device, mapping, bpm) }
}

function chain() {
	var c = {}
	c.expectInputNameEquals = function () { return c }
	c.expectOutputNameEquals = function () { return c }
	return c
}

var api = {
	mDefaults: {
		getAppName: function () { return 'Cubase' },
		mAppVersion: { getVersionString: function () { return '15.0.30-harness' } },
		getNumberOfInsertEffectSlots: function () { return 8 }
	},
	makeDeviceDriver: function () {
		var driver = {
			mPorts: {
				makeMidiInput: function () { midiInput = { mOnSysex: null }; return midiInput },
				makeMidiOutput: function () { return { sendMidi: function (dev, bytes) { sent.push(bytes.slice()) } } }
			},
			makeDetectionUnit: function () { return { detectPortPair: chain } },
			mSurface: {
				makeLabelField: function (x, y, w, h) {
					var field = { kind: 'label', x: x, y: y, w: w, h: h, related: null }
					field.relateTo = function (element) { field.related = element.kind + '@' + element.x + ',' + element.y; return field }
					surfaceElements.push(field)
					return field
				},
				makeLamp: function (x, y, w, h) {
					var lamp = { kind: 'lamp', x: x, y: y, w: w, h: h, shape: 'rectangle' }
					lamp.setShapeCircle = function () { lamp.shape = 'circle'; return lamp }
					lamp.mSurfaceValue = {
						setDisplayValue: function (dev, text) { panelLog.push({ display: text }) },
						setProcessValue: function (dev, value) { panelLog.push({ lamp: value }) }
					}
					surfaceElements.push(lamp)
					return lamp
				},
				makeCustomValueVariable: function (name) {
					return { name: name, setProcessValue: function (dev, v) { if (v > 0) fired.push(name) } }
				}
			},
			mMapping: {
				makePage: function () {
					page = {
						mHostAccess: {
							makeDirectAccess: function (hostObject) { return makeDirectAccess(hostObject) },
							mTrackSelection: {
								mMixerChannel: 'selected',
								mAction: {
									mNextTrack: { trigger: function () { var i = mixer.children.indexOf(selectedId); if (i < 2) selectedId = mixer.children[i + 1] } },
									mPrevTrack: { trigger: function () { var i = mixer.children.indexOf(selectedId); if (i > 0) selectedId = mixer.children[i - 1] } }
								}
							},
							mMixConsole: 'mixer',
							mTransport: { mTimeDisplay: timeDisplay }
						},
						setLabelFieldText: function (field, text) { field.text = text; return page },
						setLabelFieldHostObject: function (field, hostObject) { field.hostObject = String(hostObject); return page },
						makeCommandBinding: function (variable, category, name) {
							return { canPerform: function () { return category !== 'Add Track' && !(category === 'Edit' && name === 'Undo') } }
						}
					}
					return page
				}
			}
		}
		api._driver = driver
		return driver
	}
}

// ------------------------------------------------------------------ load the real script
var scriptPath = path.resolve(process.argv[2])
var originalLoad = Module._load
Module._load = function (request) {
	if (request === 'midiremote_api_v1') return api
	return originalLoad.apply(this, arguments)
}
global.console = { log: function (m) { logs.push(String(m)) }, error: function (m) { logs.push(String(m)) } }
require(scriptPath)

var driver = api._driver
if (driver.mOnActivate) driver.mOnActivate(device)
if (page.mOnActivate) page.mOnActivate(device, mapping)
;['mPrimary', 'mSecondary'].forEach(function (d) {
	;['mTransportLocator', 'mCycleLocatorLeft', 'mCycleLocatorRight'].forEach(function (f) {
		var field = timeDisplay[d][f]
		if (field.mOnChange) field.mOnChange(device, mapping, field._time, d === 'mPrimary' ? 'Compases+Tiempos' : 'Segundos')
	})
})
if (timeDisplay.mOnChangeTempoBPM) timeDisplay.mOnChangeTempoBPM(device, mapping, 120)

// ------------------------------------------------------------------ run steps (one JSON line in, one out)
var readline = require('readline')
var rl = readline.createInterface({ input: process.stdin })
rl.on('line', function (line) {
	var step = JSON.parse(line)
	sent = []
	if (step.frames) step.frames.forEach(function (f) { midiInput.mOnSysex(device, [0xF0].concat(f, [0xF7])) })
	if (step.idle) for (var i = 0; i < step.idle; i++) { page.mOnIdle(device, mapping); if (driver.mOnIdle) driver.mOnIdle(device) }
	if (step.remove) {
		objects[step.remove].removed = true
		listeners.da.forEach(function (d) { if (d.mOnObjectWillBeRemoved) d.mOnObjectWillBeRemoved(device, mapping, step.remove) })
	}
	var reply = { sent: sent, logs: logs.splice(0) }
	if (step.state) {
		reply.state = { fired: fired.slice(), selectedId: selectedId, ids: { mixer: mixer.id, out: out.id, instr: instr.id, audio: audio.id } }
		reply.state.surface = surfaceElements.map(function (e) {
			return { kind: e.kind, x: e.x, y: e.y, w: e.w, h: e.h, text: e.text, hostObject: e.hostObject, related: e.related, shape: e.shape }
		})
		reply.state.panelLog = panelLog.splice(0)
	}
	process.stdout.write(JSON.stringify(reply) + '\n')
})
