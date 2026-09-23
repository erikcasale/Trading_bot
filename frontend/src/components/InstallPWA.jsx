import { useEffect, useState } from "react";
import { Download, Share } from "lucide-react";

export default function InstallPWA() {
  const [deferred, setDeferred] = useState(null);
  const [installed, setInstalled] = useState(false);
  const [iosHint, setIosHint] = useState(false);

  useEffect(() => {
    const isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
    if (isStandalone) { setInstalled(true); return; }
    const onPrompt = (e) => { e.preventDefault(); setDeferred(e); };
    const onInstalled = () => { setInstalled(true); setDeferred(null); };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    const isIos = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
    if (isIos) setIosHint(true);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  const install = async () => {
    if (!deferred) return;
    deferred.prompt();
    await deferred.userChoice;
    setDeferred(null);
  };

  if (installed) return null;

  if (deferred) {
    return (
      <button data-testid="pwa-install-button" onClick={install}
        className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-2 rounded-lg bg-[#10B981] hover:bg-[#059669] text-white transition-colors">
        <Download className="w-3.5 h-3.5" />Installa app
      </button>
    );
  }

  if (iosHint) {
    return (
      <span data-testid="pwa-ios-hint" className="inline-flex items-center gap-1.5 text-[11px] text-[#94A3B8] border border-[#1E293B] rounded-lg px-3 py-2">
        <Share className="w-3.5 h-3.5 text-[#0EA5E9]" />Installa: Condividi → "Aggiungi a Home"
      </span>
    );
  }

  return null;
}
