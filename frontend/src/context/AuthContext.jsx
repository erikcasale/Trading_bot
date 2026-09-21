import { createContext, useContext, useEffect, useState } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=checking, false=guest, obj=auth

  useEffect(() => {
    const token = localStorage.getItem("apex_token");
    if (!token) { setUser(false); return; }
    api.get("/auth/me")
      .then((r) => setUser(r.data))
      .catch(() => { localStorage.removeItem("apex_token"); setUser(false); });
  }, []);

  const login = (token, u) => {
    localStorage.setItem("apex_token", token);
    setUser(u);
  };
  const logout = () => {
    localStorage.removeItem("apex_token");
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
