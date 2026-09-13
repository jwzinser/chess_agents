import { useEffect, useRef } from "react";
import { setToken } from "./auth";

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

function Login() {
  const buttonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const clientId = CLIENT_ID;
    if (!clientId || !buttonRef.current) return;

    let cancelled = false;

    function render(id: string) {
      if (cancelled || !window.google || !buttonRef.current) return;
      window.google.accounts.id.initialize({
        client_id: id,
        callback: (response) => setToken(response.credential),
      });
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: "outline",
        size: "large",
      });
    }

    if (window.google) {
      render(clientId);
    } else {
      const interval = setInterval(() => {
        if (window.google) {
          clearInterval(interval);
          render(clientId);
        }
      }, 100);
      return () => {
        cancelled = true;
        clearInterval(interval);
      };
    }

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="login-screen">
      <div className="login-card">
        <h1>Chess Agents</h1>
        <p>Sign in with Google to play against a local LLM and ask it questions about the position.</p>
        {CLIENT_ID ? (
          <div ref={buttonRef} className="login-button" />
        ) : (
          <p className="login-error">Missing VITE_GOOGLE_CLIENT_ID configuration.</p>
        )}
      </div>
    </div>
  );
}

export default Login;
