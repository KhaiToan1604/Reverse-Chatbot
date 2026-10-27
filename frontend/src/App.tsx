import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useUser } from "./store";
import Admin from "./pages/Admin";
import Home from "./pages/Home";
import Progress from "./pages/Progress";
import Quiz from "./pages/Quiz";
import Summary from "./pages/Summary";

export default function App() {
  const { user, setUser } = useUser();
  return (
    <Layout user={user} onLogout={() => setUser(null)}>
      <Routes>
        <Route path="/" element={<Home user={user} setUser={setUser} />} />
        <Route path="/quiz/:sid" element={<Quiz />} />
        <Route path="/summary/:sid" element={<Summary user={user} />} />
        <Route path="/progress" element={<Progress user={user} onMissingUser={() => setUser(null)} />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
