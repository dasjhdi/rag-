/**
 * Browser speech-to-text button.
 * Renders nothing when the Web Speech API is unavailable.
 */

import { useEffect, useRef, useState } from 'react';
import { Mic, MicOff } from 'lucide-react';

interface SpeechResultAlternative {
  transcript: string;
}

interface SpeechResult {
  [index: number]: SpeechResultAlternative;
  length: number;
}

interface SpeechResultList {
  [index: number]: SpeechResult;
  length: number;
}

interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: SpeechResultList;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

interface VoiceInputButtonProps {
  onTranscript: (text: string) => void;
  disabled?: boolean;
  className?: string;
}

export function VoiceInputButton({
  onTranscript,
  disabled = false,
  className = '',
}: VoiceInputButtonProps) {
  const [recognitionCtor, setRecognitionCtor] =
    useState<{ ctor: SpeechRecognitionConstructor } | null>(null);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  useEffect(() => {
    const speechWindow = window as Window & {
      SpeechRecognition?: SpeechRecognitionConstructor;
      webkitSpeechRecognition?: SpeechRecognitionConstructor;
    };
    const Ctor =
      speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition || null;
    setRecognitionCtor(Ctor ? { ctor: Ctor } : null);
    return () => {
      recognitionRef.current?.abort();
      recognitionRef.current = null;
    };
  }, []);

  if (!recognitionCtor) {
    return null;
  }

  const toggle = () => {
    if (disabled) return;
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }

    let recognition: SpeechRecognitionLike;
    try {
      recognition = new recognitionCtor.ctor();
    } catch {
      setError('当前浏览器不支持语音识别');
      return;
    }
    recognition.lang = 'zh-CN';
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      let transcript = '';
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        transcript += event.results[index][0]?.transcript ?? '';
      }
      const text = transcript.trim();
      if (text) {
        onTranscript(text);
      }
    };
    recognition.onerror = (event) => {
      setError(event.error ? `语音识别失败: ${event.error}` : '语音识别失败');
      setListening(false);
    };
    recognition.onend = () => {
      setListening(false);
      recognitionRef.current = null;
    };
    recognitionRef.current = recognition;
    setError(null);
    setListening(true);
    try {
      recognition.start();
    } catch {
      setListening(false);
      setError('无法启动语音识别');
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={disabled}
      className={`
        p-2 rounded-lg transition-all duration-200
        ${disabled
          ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
          : listening
            ? 'text-red-500 bg-red-50 dark:bg-red-900/30'
            : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-700 dark:hover:text-gray-300'
        }
        ${className}
      `}
      title={error || (listening ? '停止语音输入' : '语音输入（中文）')}
      aria-label={listening ? '停止语音输入' : '语音输入'}
    >
      {listening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
    </button>
  );
}
