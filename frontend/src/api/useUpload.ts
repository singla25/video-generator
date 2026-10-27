import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, UploadAbortedError, type UploadOptions } from './client';

type Send<T> = (options: UploadOptions) => Promise<T>;

const FALLBACK = 'Something went wrong. Please try again.';

/**
 * Run an upload with progress, a visible error and Retry. One upload at a time; cancel and
 * unmount abort the request, and an aborted request never sets state afterwards.
 */
export function useUpload<T>(onSuccess: (result: T) => void | Promise<void>) {
  const [percent, setPercent] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const last = useRef<Send<T> | null>(null);
  const success = useRef(onSuccess);
  useEffect(() => {
    success.current = onSuccess;
  });

  const cancel = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
    setPending(false);
    setPercent(0);
  }, []);

  useEffect(
    () => () => {
      controller.current?.abort();
    },
    [],
  );

  const start = useCallback(async (send: Send<T>) => {
    if (controller.current) return;
    const own = new AbortController();
    controller.current = own;
    last.current = send;
    setPending(true);
    setPercent(0);
    setError(null);
    try {
      const result = await send({ signal: own.signal, onProgress: setPercent });
      if (own.signal.aborted) return;
      controller.current = null;
      setPending(false);
      await success.current(result);
    } catch (caught) {
      if (own.signal.aborted || caught instanceof UploadAbortedError) return;
      controller.current = null;
      setPending(false);
      setError(caught instanceof ApiError ? caught.message : FALLBACK);
    }
  }, []);

  const retry = useCallback(() => {
    if (last.current) void start(last.current);
  }, [start]);

  return { start, retry, cancel, percent, error, pending };
}
