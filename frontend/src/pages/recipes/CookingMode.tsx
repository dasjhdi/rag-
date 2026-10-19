import { useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Pause,
  Play,
  TimerReset,
} from 'lucide-react';
import { useAuth } from '../../contexts';
import { getRecipe } from '../../services/api/diet';
import type { Recipe } from '../../types/diet';

type WakeLockSentinel = { release: () => Promise<void> };

function formatTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

export default function CookingModePage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const { token } = useAuth();
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timerRemaining, setTimerRemaining] = useState(0);
  const [timerLabel, setTimerLabel] = useState('');
  const [timerRunning, setTimerRunning] = useState(false);
  const wakeLockRef = useRef<WakeLockSentinel | null>(null);

  const servings = Number(searchParams.get('servings') || '0') || undefined;

  useEffect(() => {
    let cancelled = false;
    const navigatorWithWakeLock = navigator as Navigator & {
      wakeLock?: { request: (type: string) => Promise<WakeLockSentinel> };
    };
    navigatorWithWakeLock.wakeLock
      ?.request('screen')
      .then(sentinel => {
        if (!cancelled) {
          wakeLockRef.current = sentinel;
        }
      })
      .catch(() => {
        // Screen wake lock is a progressive enhancement.
      });
    return () => {
      cancelled = true;
      wakeLockRef.current?.release().catch(() => undefined);
      wakeLockRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!token || !id) return;
    let cancelled = false;
    setIsLoading(true);
    getRecipe(token, id, { servings })
      .then(data => {
        if (!cancelled) {
          setRecipe(data);
          setStepIndex(0);
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载菜谱失败');
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, id, servings]);

  useEffect(() => {
    if (!timerRunning || timerRemaining <= 0) return;
    const handle = window.setTimeout(() => {
      setTimerRemaining(value => Math.max(0, value - 1));
    }, 1000);
    return () => window.clearTimeout(handle);
  }, [timerRunning, timerRemaining]);

  useEffect(() => {
    if (timerRunning && timerRemaining === 0) {
      setTimerRunning(false);
    }
  }, [timerRunning, timerRemaining]);

  const startTimer = (seconds: number, label: string) => {
    setTimerRemaining(seconds);
    setTimerLabel(label);
    setTimerRunning(true);
  };

  const resetTimer = () => {
    setTimerRunning(false);
    setTimerRemaining(0);
    setTimerLabel('');
  };

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-950">
        <Loader2 className="w-10 h-10 animate-spin text-amber-400" />
      </div>
    );
  }

  if (error || !recipe) {
    return (
      <div className="flex-1 p-6 bg-gray-950 text-white">
        <div className="max-w-3xl mx-auto rounded-2xl bg-red-900/40 p-5">
          {error || '菜谱不存在'}
        </div>
      </div>
    );
  }

  const steps = recipe.steps;
  const currentStep = steps[stepIndex];
  const progress = steps.length ? ((stepIndex + 1) / steps.length) * 100 : 0;

  return (
    <div className="flex-1 overflow-auto bg-gray-950 text-white p-4 md:p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between gap-4">
          <Link
            to={`/recipes/${recipe.recipe_id}`}
            className="inline-flex items-center gap-1 text-sm text-gray-300 hover:text-white"
          >
            <ArrowLeft className="w-4 h-4" />
            退出烹饪模式
          </Link>
          <div className="text-sm text-gray-400">
            {recipe.title} · {recipe.servings} 人份
          </div>
        </div>

        <div className="mt-6 h-2 rounded-full bg-gray-800 overflow-hidden">
          <div
            className="h-full bg-amber-400 transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>

        {steps.length === 0 ? (
          <div className="mt-10 rounded-2xl bg-gray-900 p-6 text-gray-300">
            这道菜还没有结构化步骤，请返回详情页查看原文。
          </div>
        ) : (
          <>
            <div className="mt-6 flex items-center justify-between text-sm text-gray-400">
              <span>
                步骤 {stepIndex + 1} / {steps.length}
              </span>
              {currentStep.timer_seconds && (
                <span>建议计时 {Math.round(currentStep.timer_seconds / 60)} 分钟</span>
              )}
            </div>

            <div className="mt-4 min-h-[40vh] rounded-3xl bg-gray-900 border border-gray-800 p-6 md:p-10 flex items-center">
              <p className="text-2xl md:text-4xl leading-relaxed font-medium">
                {currentStep.text}
              </p>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <button
                onClick={() => setStepIndex(index => Math.max(0, index - 1))}
                disabled={stepIndex === 0}
                className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-gray-800 hover:bg-gray-700 disabled:opacity-40"
              >
                <ChevronLeft className="w-5 h-5" />
                上一步
              </button>
              <button
                onClick={() =>
                  setStepIndex(index => Math.min(steps.length - 1, index + 1))
                }
                disabled={stepIndex >= steps.length - 1}
                className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-amber-500 text-gray-950 font-semibold hover:bg-amber-400 disabled:opacity-40"
              >
                下一步
                <ChevronRight className="w-5 h-5" />
              </button>
              {currentStep.timer_seconds && (
                <button
                  onClick={() =>
                    startTimer(
                      currentStep.timer_seconds ?? 0,
                      `步骤 ${currentStep.index}`
                    )
                  }
                  className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-gray-800 hover:bg-gray-700"
                >
                  <Play className="w-5 h-5" />
                  开始计时
                </button>
              )}
            </div>

            {(timerRemaining > 0 || timerLabel) && (
              <div className="mt-8 rounded-3xl bg-gray-900 border border-amber-500/30 p-6 flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="text-sm text-gray-400">{timerLabel}</div>
                  <div className="text-5xl font-mono font-bold text-amber-300 mt-1">
                    {formatTime(timerRemaining)}
                  </div>
                  {timerRemaining === 0 && (
                    <div className="text-sm text-green-400 mt-1">时间到</div>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setTimerRunning(value => !value)}
                    disabled={timerRemaining === 0}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 disabled:opacity-40"
                  >
                    {timerRunning ? (
                      <Pause className="w-4 h-4" />
                    ) : (
                      <Play className="w-4 h-4" />
                    )}
                    {timerRunning ? '暂停' : '继续'}
                  </button>
                  <button
                    onClick={resetTimer}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gray-800 hover:bg-gray-700"
                  >
                    <TimerReset className="w-4 h-4" />
                    重置
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
