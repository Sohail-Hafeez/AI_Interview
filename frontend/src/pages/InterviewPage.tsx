import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import * as faceapi from 'face-api.js'
import Brand from '../components/Brand'
import ScoreRing from '../components/ScoreRing'
import '../App.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const SPEAKER_TEST_MESSAGE = 'This is a speaker test. Can you hear this message clearly?'
const MIC_CHECK_PHRASE = 'Hello, I am a professional AI Expert'
const FACE_MODEL_URL = 'https://justadudewhohacks.github.io/face-api.js/models'

const RULES = [
  'The interview may take 5-15 minutes to complete.',
  'Be calm and use a quiet place with minimal background noise.',
  'Once started, you cannot go back to a previous question.',
  'You cannot re-take this interview once submitted.',
  'Make sure your camera, microphone, and speaker are working and your internet connection is stable.',
  'Cheating or use of AI tools during the interview is strictly forbidden.',
  'You are not allowed to switch tabs or minimize/maximize the window — this will be recorded.',
  'Your responses will be recorded and evaluated by an AI interviewer.',
]

type Screen =
  | 'loading'
  | 'invalid'
  | 'completed'
  | 'disqualified'
  | 'welcome'
  | 'camera-check'
  | 'speaker-check'
  | 'mic-check'
  | 'network-check'
  | 'ready'
  | 'interview'
  | 'result'

const CAMERA_ACTIVE_SCREENS: Screen[] = [
  'camera-check',
  'speaker-check',
  'mic-check',
  'network-check',
  'ready',
  'interview',
]

const STEPS: { screen: Screen; label: string }[] = [
  { screen: 'camera-check', label: 'Camera' },
  { screen: 'speaker-check', label: 'Speaker' },
  { screen: 'mic-check', label: 'Microphone' },
  { screen: 'network-check', label: 'Network' },
  { screen: 'ready', label: 'Ready' },
  { screen: 'interview', label: 'Interview' },
]

const PREFERRED_FEMALE_VOICES = [
  'Microsoft AriaNeural',
  'Microsoft JennyNeural',
  'Microsoft Zira',
  'Google US English Female',
  'Samantha',
  'Google UK English Female',
]

let cachedFemaleVoice: SpeechSynthesisVoice | null | undefined

function getFemaleVoice(): SpeechSynthesisVoice | null {
  if (cachedFemaleVoice !== undefined) return cachedFemaleVoice

  const voices = window.speechSynthesis.getVoices()
  if (voices.length === 0) return null

  for (const name of PREFERRED_FEMALE_VOICES) {
    const match = voices.find((v) => v.name.includes(name))
    if (match) {
      cachedFemaleVoice = match
      return match
    }
  }

  const fallback = voices.find((v) => /female/i.test(v.name)) ?? null
  cachedFemaleVoice = fallback
  return fallback
}

function speak(text: string) {
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  const voice = getFemaleVoice()
  if (voice) utterance.voice = voice
  window.speechSynthesis.speak(utterance)
}

function InterviewPage() {
  const { token } = useParams<{ token: string }>()
  const [screen, setScreen] = useState<Screen>('loading')
  const [candidateName, setCandidateName] = useState('')
  const [role, setRole] = useState('')
  const [totalQuestions, setTotalQuestions] = useState(0)
  const [questionNumber, setQuestionNumber] = useState(1)
  const [question, setQuestion] = useState('')
  const [transcript, setTranscript] = useState('')
  const [comment, setComment] = useState('')
  const [score, setScore] = useState<number | null>(null)
  const [summary, setSummary] = useState('')
  const [recording, setRecording] = useState(false)
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [micCheckTranscript, setMicCheckTranscript] = useState('')
  const [faceCount, setFaceCount] = useState<number | null>(null)
  const [cameraStatus, setCameraStatus] = useState('Loading face detection...')
  const [networkSpeed, setNetworkSpeed] = useState<string | null>(null)
  const [tabWarnings, setTabWarnings] = useState(0)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const cameraStreamRef = useRef<MediaStream | null>(null)
  const faceCheckIntervalRef = useRef<number | null>(null)

  useEffect(() => {
    async function loadCandidate() {
      try {
        const res = await fetch(`${API_BASE}/api/candidates/${token}`)
        if (!res.ok) {
          setScreen('invalid')
          return
        }
        const data = await res.json()
        setCandidateName(data.name)
        setRole(data.role)
        if (data.status === 'completed') {
          setScore(data.score)
          setSummary(data.summary)
          setScreen('completed')
        } else if (data.status === 'disqualified') {
          setSummary(data.summary)
          setScreen('disqualified')
        } else {
          setScreen('welcome')
        }
      } catch {
        setScreen('invalid')
      }
    }
    loadCandidate()
  }, [token])

  async function disqualify(reason: string) {
    stopCamera()
    const formData = new FormData()
    formData.append('reason', reason)
    await fetch(`${API_BASE}/api/candidates/${token}/disqualify`, { method: 'POST', body: formData })
    setSummary(`Disqualified: ${reason}`)
    setScreen('disqualified')
  }

  function stopCamera() {
    if (faceCheckIntervalRef.current) {
      window.clearInterval(faceCheckIntervalRef.current)
      faceCheckIntervalRef.current = null
    }
    cameraStreamRef.current?.getTracks().forEach((t) => t.stop())
    cameraStreamRef.current = null
  }

  async function startCameraMonitoring() {
    setCameraStatus('Loading face detection...')
    await faceapi.nets.tinyFaceDetector.loadFromUri(FACE_MODEL_URL)

    setCameraStatus('Starting camera...')
    const stream = await navigator.mediaDevices.getUserMedia({ video: true })
    cameraStreamRef.current = stream
    if (videoRef.current) {
      videoRef.current.srcObject = stream
    }

    setCameraStatus('Monitoring active')
    faceCheckIntervalRef.current = window.setInterval(async () => {
      if (!videoRef.current) return
      const detections = await faceapi.detectAllFaces(
        videoRef.current,
        new faceapi.TinyFaceDetectorOptions(),
      )
      setFaceCount(detections.length)
      if (detections.length >= 2) {
        disqualify('Multiple faces detected by camera monitoring')
      }
    }, 1000)
  }

  useEffect(() => {
    if (CAMERA_ACTIVE_SCREENS.includes(screen) && !cameraStreamRef.current) {
      startCameraMonitoring()
    }
    if (!CAMERA_ACTIVE_SCREENS.includes(screen)) {
      stopCamera()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen])

  function playSpeakerTest() {
    speak(SPEAKER_TEST_MESSAGE)
  }

  function confirmSpeakerCheck() {
    fetch(`${API_BASE}/api/candidates/${token}/speaker-check`, { method: 'POST' })
    setScreen('mic-check')
  }

  async function startMicCheckRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    audioChunksRef.current = []
    const mediaRecorder = new MediaRecorder(stream)
    mediaRecorder.ondataavailable = (e) => audioChunksRef.current.push(e.data)
    mediaRecorder.start()
    mediaRecorderRef.current = mediaRecorder
    setRecording(true)
    setMicCheckTranscript('')
    setStatus('Recording...')
  }

  async function stopMicCheckRecording() {
    const mediaRecorder = mediaRecorderRef.current
    if (!mediaRecorder) return

    setRecording(false)
    setBusy(true)
    setStatus('Checking microphone...')

    mediaRecorder.onstop = async () => {
      mediaRecorder.stream.getTracks().forEach((t) => t.stop())

      const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
      const formData = new FormData()
      formData.append('audio', audioBlob, 'mic_check.webm')

      try {
        const res = await fetch(`${API_BASE}/api/mic-check`, { method: 'POST', body: formData })
        if (!res.ok) throw new Error(`Server error (${res.status})`)
        const data = await res.json()
        setMicCheckTranscript(data.transcript)
        setStatus('')
      } catch (err) {
        setStatus(`Mic check failed: ${err instanceof Error ? err.message : String(err)}`)
      } finally {
        setBusy(false)
      }
    }

    mediaRecorder.stop()
  }

  async function runNetworkTest() {
    setNetworkSpeed(null)
    setStatus('Testing your connection...')
    const start = performance.now()
    const res = await fetch(`${API_BASE}/api/network-test-file?t=${Date.now()}`, { cache: 'no-store' })
    const blob = await res.blob()
    const seconds = (performance.now() - start) / 1000
    const kilobits = (blob.size * 8) / 1000
    const speedKbps = kilobits / seconds
    setNetworkSpeed(
      speedKbps > 1000 ? `${(speedKbps / 1000).toFixed(2)} Mbps` : `${speedKbps.toFixed(0)} Kbps`,
    )
    setStatus('')

    const formData = new FormData()
    formData.append('speed_kbps', String(speedKbps))
    fetch(`${API_BASE}/api/candidates/${token}/network-check`, { method: 'POST', body: formData })
  }

  useEffect(() => {
    if (screen === 'network-check') {
      runNetworkTest()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen])

  async function beginInterview() {
    setBusy(true)
    setStatus('Starting interview...')

    const res = await fetch(`${API_BASE}/api/candidates/${token}/start`, { method: 'POST' })
    const data = await res.json()

    setTotalQuestions(data.total_questions)
    setQuestionNumber(data.question_number)
    setQuestion(data.question)
    setBusy(false)
    setStatus('')
    setScreen('interview')
    speak(data.question)
  }

  useEffect(() => {
    if (screen !== 'interview') return

    function flagTabSwitch() {
      if (document.hidden) {
        setTabWarnings((n) => n + 1)
        const formData = new FormData()
        formData.append('reason', 'Tab switch / window blur detected during interview')
        fetch(`${API_BASE}/api/candidates/${token}/flag`, { method: 'POST', body: formData })
      }
    }

    document.addEventListener('visibilitychange', flagTabSwitch)
    return () => document.removeEventListener('visibilitychange', flagTabSwitch)
  }, [screen, token])

  async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    audioChunksRef.current = []
    const mediaRecorder = new MediaRecorder(stream)
    mediaRecorder.ondataavailable = (e) => audioChunksRef.current.push(e.data)
    mediaRecorder.start()
    mediaRecorderRef.current = mediaRecorder
    setRecording(true)
    setStatus('Recording...')
  }

  async function stopRecordingAndSubmit() {
    const mediaRecorder = mediaRecorderRef.current
    if (!mediaRecorder) return

    setRecording(false)
    setBusy(true)
    setStatus('Processing...')

    mediaRecorder.onstop = async () => {
      mediaRecorder.stream.getTracks().forEach((t) => t.stop())

      const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
      const formData = new FormData()
      formData.append('audio', audioBlob, 'answer.webm')

      let failed = false
      try {
        const res = await fetch(`${API_BASE}/api/candidates/${token}/answer`, {
          method: 'POST',
          body: formData,
        })
        if (!res.ok) {
          throw new Error(`Server error (${res.status})`)
        }
        const data = await res.json()

        setTranscript(data.transcript)
        setComment(data.comment)

        if (data.finished) {
          setScore(data.score)
          setSummary(data.summary)
          speak(`Interview complete. Your score is ${data.score} out of 10. ${data.summary}`)
          setScreen('result')
        } else {
          setQuestionNumber(data.question_number)
          setQuestion(data.question)
          speak(`${data.comment}. ${data.question}`)
        }
      } catch {
        failed = true
        setStatus('Something went wrong, please try recording your answer again.')
      } finally {
        setBusy(false)
        if (!failed) setStatus('')
      }
    }

    mediaRecorder.stop()
  }

  if (screen === 'loading') {
    return (
      <div className="app">
        <p>Loading...</p>
      </div>
    )
  }

  if (screen === 'invalid') {
    return (
      <div className="app">
        <h1>Invalid Link</h1>
        <p>This interview link is not valid. Please check the link from your email.</p>
      </div>
    )
  }

  if (screen === 'completed') {
    return (
      <div className="app">
        <Brand />
        <h2>Interview Already Completed</h2>
        <ScoreRing score={score ?? 0} />
        <p>{summary}</p>
      </div>
    )
  }

  if (screen === 'disqualified') {
    return (
      <div className="app">
        <Brand />
        <h2>Interview Ended</h2>
        <p className="warning-banner">{summary}</p>
      </div>
    )
  }

  return (
    <div className="app">
      <Brand subtitle={role ? `Interview for ${role}` : undefined} />
      <h1>AI Interview</h1>

      {CAMERA_ACTIVE_SCREENS.includes(screen) && (
        <div className="stepper">
          {STEPS.map((step) => {
            const currentIndex = STEPS.findIndex((s) => s.screen === screen)
            const stepIndex = STEPS.findIndex((s) => s.screen === step.screen)
            const state =
              stepIndex < currentIndex ? 'done' : stepIndex === currentIndex ? 'active' : ''
            return (
              <div key={step.screen} className={`step ${state}`}>
                {step.label}
              </div>
            )
          })}
        </div>
      )}

      {screen === 'welcome' && (
        <div className="panel">
          <h2>
            Thanks {candidateName} for applying for the {role} in NLC
          </h2>
          <p>Before you begin, please read the following instructions carefully:</p>
          <ul className="rules-list">
            {RULES.map((rule) => (
              <li key={rule}>{rule}</li>
            ))}
          </ul>
          <button onClick={() => setScreen('camera-check')}>Proceed</button>
        </div>
      )}

      {CAMERA_ACTIVE_SCREENS.includes(screen) && (
        <div className="interview-layout">
          <div className="main-column">
            {screen === 'camera-check' && (
              <div className="panel">
                <h2>Camera Check</h2>
                <p className="status">{cameraStatus}</p>
                {faceCount !== null && <p>Faces detected: {faceCount}</p>}
                <p>Your camera will stay on and be monitored for the rest of the interview.</p>
                <button onClick={() => setScreen('speaker-check')} disabled={faceCount !== 1}>
                  Continue
                </button>
              </div>
            )}

            {screen === 'speaker-check' && (
              <div className="panel">
                <h2>Speaker Check</h2>
                <p>Click the button below and make sure you can hear the message clearly.</p>
                <button onClick={playSpeakerTest}>Play Test Sound</button>
                <div className="button-row">
                  <button onClick={confirmSpeakerCheck}>Yes, I can hear it</button>
                  <button className="secondary" onClick={playSpeakerTest}>
                    I can't hear anything
                  </button>
                </div>
              </div>
            )}

            {screen === 'mic-check' && (
              <div className="panel">
                <h2>Microphone Check</h2>
                <p>
                  Please say: <strong>"{MIC_CHECK_PHRASE}"</strong>
                </p>
                <button
                  className={recording ? 'recording' : ''}
                  onClick={recording ? stopMicCheckRecording : startMicCheckRecording}
                  disabled={busy && !recording}
                >
                  {recording && <span className="recording-dot" />}
                  {recording ? 'Stop & Check' : 'Start Recording'}
                </button>
                <p className="status">{status}</p>

                {micCheckTranscript && (
                  <>
                    <div className="transcript">We heard: "{micCheckTranscript}"</div>
                    <div className="button-row">
                      <button onClick={() => setScreen('network-check')}>
                        Sounds Good, Continue
                      </button>
                      <button className="secondary" onClick={startMicCheckRecording}>
                        Try Again
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {screen === 'network-check' && (
              <div className="panel">
                <h2>Network Speed Check</h2>
                <p className="status">{status}</p>
                {networkSpeed && <p>Your connection speed: {networkSpeed}</p>}
                <div className="button-row">
                  <button onClick={() => setScreen('ready')} disabled={!networkSpeed}>
                    Continue
                  </button>
                  <button className="secondary" onClick={runNetworkTest}>
                    Retest
                  </button>
                </div>
              </div>
            )}

            {screen === 'ready' && (
              <div className="panel">
                <p>
                  Hi {candidateName}, you're about to begin your interview for the{' '}
                  <strong>{role}</strong> role.
                </p>
                <button onClick={beginInterview} disabled={busy}>
                  Begin Interview
                </button>
              </div>
            )}

            {screen === 'interview' && (
              <div className="panel">
                {tabWarnings > 0 && (
                  <p className="warning-banner">
                    Tab switch detected ({tabWarnings}) — this has been recorded.
                  </p>
                )}
                <div className="progress-track">
                  <div
                    className="progress-fill"
                    style={{ width: `${(questionNumber / totalQuestions) * 100}%` }}
                  />
                </div>
                <p className="progress-label">
                  Question {questionNumber} of {totalQuestions}
                </p>
                <div className="question">{question}</div>
                {transcript && <div className="transcript">You said: {transcript}</div>}
                {comment && <div className="comment">{comment}</div>}
                <button
                  className={recording ? 'recording' : ''}
                  onClick={recording ? stopRecordingAndSubmit : startRecording}
                  disabled={busy && !recording}
                >
                  {recording && <span className="recording-dot" />}
                  {recording ? 'Stop & Submit' : 'Start Recording'}
                </button>
                <p className="status">{status}</p>
              </div>
            )}
          </div>

          <div className="camera-sidebar">
            <video ref={videoRef} className="video-preview" autoPlay muted playsInline />
            <p className="status">{cameraStatus}</p>
            {faceCount !== null && <p>Faces detected: {faceCount}</p>}
          </div>
        </div>
      )}

      {screen === 'result' && (
        <div className="panel">
          <h2>Interview Complete</h2>
          <ScoreRing score={score ?? 0} />
          <p>{summary}</p>
        </div>
      )}
    </div>
  )
}

export default InterviewPage
