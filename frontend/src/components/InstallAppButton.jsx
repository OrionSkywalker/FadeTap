import { useEffect, useState } from "react";

function isStandalone() {
  return window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

export default function InstallAppButton() {
  const [installPrompt, setInstallPrompt] = useState(null);
  const [installed, setInstalled] = useState(() => isStandalone());
  const [isIos, setIsIos] = useState(false);

  useEffect(() => {
    const onBeforeInstallPrompt = (event) => {
      event.preventDefault();
      setInstallPrompt(event);
    };
    const onAppInstalled = () => {
      setInstalled(true);
      setInstallPrompt(null);
    };

    setIsIos(/iPad|iPhone|iPod/.test(window.navigator.userAgent) && !window.MSStream);
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onAppInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onAppInstalled);
    };
  }, []);

  async function installApp() {
    if (!installPrompt) return;
    installPrompt.prompt();
    await installPrompt.userChoice;
    setInstallPrompt(null);
  }

  if (installed) return null;

  if (isIos) {
    return (
      <p className="max-w-sm text-sm leading-6 text-zinc-600 dark:text-zinc-300">
        To install FadeTap, tap Share in Safari, then choose <span className="font-semibold">Add to Home Screen</span>.
      </p>
    );
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <button
        type="button"
        onClick={installApp}
        disabled={!installPrompt}
        className="rounded-md border border-emerald-800 px-5 py-3 text-sm font-semibold text-emerald-800 transition hover:bg-emerald-50 disabled:cursor-not-allowed disabled:border-zinc-300 disabled:text-zinc-500 disabled:hover:bg-transparent dark:border-emerald-400 dark:text-emerald-300 dark:disabled:border-zinc-700 dark:disabled:text-zinc-500 dark:hover:bg-emerald-950"
      >
        Install FadeTap app
      </button>
      {!installPrompt && (
        <p className="max-w-sm text-xs leading-5 text-zinc-500 dark:text-zinc-400">
          Installation will be available after this page finishes loading in a supported browser.
        </p>
      )}
    </div>
  );
}
