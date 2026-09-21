import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Activity, ShieldCheck, Cpu, Zap, Loader2, ArrowRight } from "lucide-react";

const DEMO = { email: "demo@apexflow.io", password: "apexflow2026" };

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (creds, register = false) => {
    setLoading(true);
    try {
      const path = register ? "/auth/register" : "/auth/login";
      const body = register ? { ...creds, name: name || "Trader" } : creds;
      const { data } = await api.post(path, body);
      login(data.token, data.user);
      toast.success("Accesso al terminale riuscito");
      navigate("/");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#080B10] flex items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute inset-0 grid-bg opacity-40" />
      <div className="absolute -top-40 -left-40 w-[500px] h-[500px] rounded-full"
           style={{ background: "radial-gradient(circle, rgba(14,165,233,0.12), transparent 70%)" }} />
      <div className="absolute -bottom-40 -right-40 w-[500px] h-[500px] rounded-full"
           style={{ background: "radial-gradient(circle, rgba(16,185,129,0.10), transparent 70%)" }} />

      <div className="relative w-full max-w-md fade-up">
        <div className="flex items-center gap-3 mb-6 justify-center">
          <div className="w-11 h-11 rounded-xl bg-[#0EA5E9]/10 border border-[#0EA5E9]/40 flex items-center justify-center">
            <Activity className="w-6 h-6 text-[#0EA5E9]" />
          </div>
          <div>
            <h1 className="font-head text-2xl font-extrabold tracking-tight leading-none">Apex Flow</h1>
            <span className="overline">Institutional Smart Money Terminal</span>
          </div>
        </div>

        <div className="card p-8 shadow-2xl">
          <div className="flex gap-1 p-1 rounded-lg bg-[#0B0E17] border border-[#1E293B] mb-6">
            {["login", "register"].map((m) => (
              <button key={m} data-testid={`auth-tab-${m}`} onClick={() => setMode(m)}
                className={`flex-1 py-2 rounded-md text-sm font-semibold transition-colors ${
                  mode === m ? "bg-[#131A24] text-white" : "text-[#64748B] hover:text-[#94A3B8]"}`}>
                {m === "login" ? "Accedi" : "Registrati"}
              </button>
            ))}
          </div>

          <form onSubmit={(e) => { e.preventDefault(); submit({ email, password }, mode === "register"); }}
                className="space-y-4">
            {mode === "register" && (
              <div>
                <label className="overline block mb-1.5">Nome</label>
                <input data-testid="auth-name-input" value={name} onChange={(e) => setName(e.target.value)}
                  placeholder="Il tuo nome"
                  className="w-full bg-[#0B0E17] border border-[#1E293B] rounded-lg px-3 py-2.5 text-sm outline-none focus:border-[#0EA5E9] transition-colors" />
              </div>
            )}
            <div>
              <label className="overline block mb-1.5">Email</label>
              <input data-testid="login-email-input" type="email" value={email} required
                onChange={(e) => setEmail(e.target.value)} placeholder="nome@broker.io"
                className="w-full bg-[#0B0E17] border border-[#1E293B] rounded-lg px-3 py-2.5 text-sm outline-none focus:border-[#0EA5E9] transition-colors" />
            </div>
            <div>
              <label className="overline block mb-1.5">Password</label>
              <input data-testid="login-password-input" type="password" value={password} required
                onChange={(e) => setPassword(e.target.value)} placeholder="••••••••"
                className="w-full bg-[#0B0E17] border border-[#1E293B] rounded-lg px-3 py-2.5 text-sm outline-none focus:border-[#0EA5E9] transition-colors" />
            </div>

            <button data-testid="login-submit-button" type="submit" disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-[#0EA5E9] hover:bg-[#0284C7] text-white font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-60">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <>
                {mode === "login" ? "Entra nel Terminale" : "Crea Account"} <ArrowRight className="w-4 h-4" /></>}
            </button>
          </form>

          <div className="flex items-center gap-3 my-5">
            <div className="flex-1 h-px bg-[#1E293B]" />
            <span className="overline">oppure</span>
            <div className="flex-1 h-px bg-[#1E293B]" />
          </div>

          <button data-testid="login-demo-submit-button" onClick={() => { setEmail(DEMO.email); setPassword(DEMO.password); submit(DEMO); }}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-[#131A24] hover:bg-[#1A2332] border border-[#334155] text-[#10B981] font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-60">
            <Zap className="w-4 h-4" /> Entra con Account Demo ($100.000)
          </button>

          <div className="grid grid-cols-3 gap-2 mt-6 text-center">
            {[[ShieldCheck, "256-bit"], [Cpu, "Claude 4.6"], [Activity, "Tickmill ECN"]].map(([Icon, t], i) => (
              <div key={i} className="flex flex-col items-center gap-1 text-[#64748B]">
                <Icon className="w-4 h-4" />
                <span className="text-[10px] font-mono">{t}</span>
              </div>
            ))}
          </div>
        </div>

        <p className="text-[11px] text-[#64748B] leading-relaxed mt-4 text-center px-2">
          ⚠️ Ambiente <span className="text-[#94A3B8]">dimostrativo</span>. Le metriche di winrate e i risultati
          sono <span className="text-[#94A3B8]">simulati</span> a scopo educativo: nessun sistema di trading
          garantisce profitti. Il trading comporta rischio di perdita del capitale.
        </p>
      </div>
    </div>
  );
}
