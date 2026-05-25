"use client";
import { useState, useRef, useEffect } from "react";
import { Send, ThumbsUp, ThumbsDown, Loader2, MessageSquare, Plus } from "lucide-react";
import Navbar from "@/components/ui/Navbar";
import SourceCard from "@/components/ui/SourceCard";
import ConfidenceBadge from "@/components/ui/ConfidenceBadge";
import { chat as chatApi } from "@/lib/api";
import type { ChatMessage, ChatSession } from "@/lib/api";
import clsx from "clsx";

export default function ChatPage() {
  const [sessions, setSessions]   = useState<ChatSession[]>([]);
  const [activeId, setActiveId]   = useState<string | null>(null);
  const [messages, setMessages]   = useState<ChatMessage[]>([]);
  const [input, setInput]         = useState("");
  const [sending, setSending]     = useState(false);
  const [feedback, setFeedback]   = useState<Record<string, "up" | "down">>({});
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatApi.sessions().then(setSessions).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadSession = async (id: string) => {
    setActiveId(id);
    const msgs = await chatApi.messages(id);
    setMessages(msgs);
  };

  const sendMessage = async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput("");
    setSending(true);

    const userMsg: ChatMessage = {
      id: `tmp-${Date.now()}`, role: "user", content: text,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);

    // 占位 AI 消息（用于流式更新）
    const placeholderId = `streaming-${Date.now()}`;
    const placeholder: ChatMessage = {
      id: placeholderId, role: "assistant", content: "",
      created_at: new Date().toISOString(),
      sources: [],
    };
    setMessages(prev => [...prev, placeholder]);

    try {
      let accumulated = "";

      for await (const { event, data } of chatApi.streamMessage(text, activeId ?? undefined)) {
        if (event === "session" && !activeId) {
          setActiveId(data.session_id);
        }
        if (event === "sources") {
          setMessages(prev => prev.map(m =>
            m.id === placeholderId ? { ...m, sources: data.sources } : m
          ));
        }
        if (event === "token") {
          accumulated += data.text;
          setMessages(prev => prev.map(m =>
            m.id === placeholderId ? { ...m, content: accumulated } : m
          ));
        }
        if (event === "done") {
          setMessages(prev => prev.map(m =>
            m.id === placeholderId
              ? { ...m, id: data.message_id, confidence: data.confidence, latency_ms: data.latency_ms }
              : m
          ));
          if (!activeId) chatApi.sessions().then(setSessions);
        }
        if (event === "error") {
          setMessages(prev => prev.map(m =>
            m.id === placeholderId ? { ...m, content: `错误：${data.message}` } : m
          ));
        }
      }
    } catch (e) {
      setMessages(prev => prev.map(m =>
        m.id === placeholderId
          ? { ...m, content: `请求失败：${e instanceof Error ? e.message : "未知错误"}` }
          : m
      ));
    } finally {
      setSending(false);
    }
  };

  const submitFeedback = async (msgId: string, rating: "up" | "down") => {
    await chatApi.feedback(msgId, rating);
    setFeedback(prev => ({ ...prev, [msgId]: rating }));
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <Navbar />

      <div className="flex flex-1 max-w-6xl mx-auto w-full gap-0">
        {/* Sidebar: session list */}
        <aside className="w-56 bg-white border-r border-gray-200 flex flex-col py-3 hidden md:flex">
          <div className="px-3 mb-2">
            <button
              onClick={() => { setActiveId(null); setMessages([]); }}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-brand-600 hover:bg-brand-50 transition-colors font-medium"
            >
              <Plus className="w-4 h-4" /> 新对话
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-3 space-y-1">
            {sessions.map(s => (
              <button key={s.id} onClick={() => loadSession(s.id)}
                className={clsx(
                  "w-full text-left px-3 py-2 rounded-lg text-xs transition-colors truncate",
                  activeId === s.id ? "bg-brand-50 text-brand-700 font-medium" : "text-gray-600 hover:bg-gray-100"
                )}>
                <div className="truncate">{s.title}</div>
                <div className="text-gray-400 mt-0.5">{s.message_count} 条消息</div>
              </button>
            ))}
          </div>
        </aside>

        {/* Chat area */}
        <div className="flex-1 flex flex-col">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && (
              <div className="h-full flex flex-col items-center justify-center text-center text-gray-400 py-16">
                <MessageSquare className="w-12 h-12 mb-4 opacity-20" />
                <p className="text-sm font-medium text-gray-500">开始提问</p>
                <p className="text-xs mt-1">可以询问零件兼容性、规格参数、价格库存等</p>
                <div className="mt-4 flex flex-col gap-2 text-xs">
                  {["丰田凯美瑞 2020 的前刹车片有哪些选择？", "Bosch 和 Brembo 刹车片有什么区别？", "这个型号 BP-BOC-45231 还有库存吗？"].map(q => (
                    <button key={q} onClick={() => setInput(q)}
                      className="px-4 py-2 bg-white border border-gray-200 rounded-lg hover:border-brand-300 hover:text-brand-600 transition-colors text-left">
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map(msg => (
              <div key={msg.id} className={clsx("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}>
                {msg.role === "assistant" && (
                  <div className="w-7 h-7 rounded-full bg-brand-500 flex items-center justify-center flex-shrink-0 mt-1">
                    <span className="text-white text-xs">AI</span>
                  </div>
                )}

                <div className={clsx("max-w-lg", msg.role === "user" ? "order-first" : "")}>
                  <div className={clsx(
                    "px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap",
                    msg.role === "user"
                      ? "bg-brand-500 text-white rounded-br-md"
                      : "bg-white border border-gray-200 text-gray-800 rounded-bl-md shadow-sm"
                  )}>
                    {msg.content || (msg.role === "assistant" && <Loader2 className="w-4 h-4 animate-spin text-brand-400 inline" />)}
                  </div>

                  {/* Assistant metadata */}
                  {msg.role === "assistant" && (
                    <div className="mt-2 space-y-2">
                      {/* Sources */}
                      {msg.sources && msg.sources.length > 0 && (
                        <div className="grid grid-cols-1 gap-1.5">
                          {msg.sources.slice(0, 3).map(src => (
                            <SourceCard key={src.id} source={src} />
                          ))}
                        </div>
                      )}

                      {/* Footer: confidence + feedback + latency */}
                      <div className="flex items-center gap-3 flex-wrap">
                        {msg.confidence != null && (
                          <ConfidenceBadge confidence={msg.confidence} />
                        )}
                        {msg.latency_ms && (
                          <span className="text-xs text-gray-400">{msg.latency_ms}ms</span>
                        )}
                        {msg.id && !msg.id.startsWith("tmp") && !msg.id.startsWith("streaming") && !msg.id.startsWith("err") && (
                          <div className="flex items-center gap-1 ml-auto">
                            <button onClick={() => submitFeedback(msg.id, "up")}
                              className={clsx("p-1 rounded transition-colors",
                                feedback[msg.id] === "up" ? "text-green-600" : "text-gray-400 hover:text-green-500")}>
                              <ThumbsUp className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => submitFeedback(msg.id, "down")}
                              className={clsx("p-1 rounded transition-colors",
                                feedback[msg.id] === "down" ? "text-red-500" : "text-gray-400 hover:text-red-400")}>
                              <ThumbsDown className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}

            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div className="border-t border-gray-200 bg-white p-4">
            <div className="flex gap-3 items-end max-w-3xl mx-auto">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
                placeholder="输入问题... (Enter 发送，Shift+Enter 换行)"
                rows={1}
                className="flex-1 resize-none border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent"
                style={{ maxHeight: "120px" }}
              />
              <button onClick={sendMessage} disabled={sending || !input.trim()}
                className="bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white p-3 rounded-xl transition-colors flex-shrink-0">
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
