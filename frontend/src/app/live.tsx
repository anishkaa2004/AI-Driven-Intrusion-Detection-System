// Real-time channel. Reconnects with exponential backoff; after a reconnect it
// emits a "resync" so pages refetch anything missed while disconnected. Pages
// also poll slowly whenever the socket is not live (fallback).
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { getToken } from "../services/api";
import type { LiveMessage } from "../types";

export type LiveStatus = "connecting" | "live" | "reconnecting";
type Listener = (msg: LiveMessage | { type: "resync" }) => void;

interface LiveState {
  status: LiveStatus;
  lastMessageAt: number | null;
  subscribe: (fn: Listener) => () => void;
}

const LiveContext = createContext<LiveState | null>(null);

export function LiveProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<LiveStatus>("connecting");
  const [lastMessageAt, setLast] = useState<number | null>(null);
  const listeners = useRef(new Set<Listener>());

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry = 0;
    let timer: number | undefined;
    let ping: number | undefined;
    let closed = false;
    let wasLive = false;

    const emit = (m: LiveMessage | { type: "resync" }) => listeners.current.forEach((l) => l(m));

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws/events`);
      ws.onopen = () => ws?.send(JSON.stringify({ type: "auth", token: getToken() }));
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data) as LiveMessage;
        setLast(Date.now());
        if (msg.type === "ready") {
          setStatus("live");
          if (wasLive) emit({ type: "resync" });
          wasLive = true;
          retry = 0;
          ping = window.setInterval(() => ws?.readyState === 1 && ws.send("ping"), 25_000);
          return;
        }
        emit(msg);
      };
      ws.onclose = () => {
        window.clearInterval(ping);
        if (closed) return;
        setStatus("reconnecting");
        const delay = Math.min(30_000, 1000 * 2 ** retry++) * (0.75 + Math.random() * 0.5);
        timer = window.setTimeout(connect, delay);
      };
    };
    connect();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      window.clearInterval(ping);
      ws?.close();
    };
  }, []);

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => void listeners.current.delete(fn);
  }, []);

  return <LiveContext.Provider value={{ status, lastMessageAt, subscribe }}>{children}</LiveContext.Provider>;
}

export function useLive() {
  const ctx = useContext(LiveContext);
  if (!ctx) throw new Error("useLive outside LiveProvider");
  return ctx;
}

/** Subscribe to live messages; handler identity may change freely. */
export function useLiveMessages(handler: Listener) {
  const { subscribe } = useLive();
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => subscribe((m) => ref.current(m)), [subscribe]);
}

/** Calls `fn` on an interval only while the live channel is down. */
export function useFallbackPolling(fn: () => void, ms = 30_000) {
  const { status } = useLive();
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (status === "live") return;
    const id = window.setInterval(() => ref.current(), ms);
    return () => window.clearInterval(id);
  }, [status, ms]);
}
