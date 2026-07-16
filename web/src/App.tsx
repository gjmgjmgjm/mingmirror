import { Routes, Route, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { ChartProvider } from "./contexts/ChartContext";
import Dashboard from "./pages/Dashboard";
import Chart from "./pages/Chart";
import Council from "./pages/Council";
import Sandbox from "./pages/Sandbox";
import Calendar from "./pages/Calendar";
import Qizheng from "./pages/Qizheng";
import QizhengYearly from "./pages/QizhengYearly";
import Ziwei from "./pages/Ziwei";
import Cases from "./pages/Cases";
import Script from "./pages/Script";
import Events from "./pages/Events";

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <div key={location.pathname} className="animate-page-enter">
      <Routes location={location}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/chart" element={<Chart />} />
        <Route path="/chart/report" element={<Chart />} />
        <Route path="/chart/yearly" element={<Chart />} />
        <Route path="/qizheng" element={<Qizheng />} />
        <Route path="/qizheng/yearly" element={<QizhengYearly />} />
        <Route path="/ziwei" element={<Ziwei />} />
        <Route path="/cases" element={<Cases />} />
        <Route path="/council" element={<Council />} />
        <Route path="/sandbox" element={<Sandbox />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/script" element={<Script />} />
        <Route path="/events" element={<Events />} />
      </Routes>
    </div>
  );
}

function App() {
  return (
    <ChartProvider>
      <Layout>
        <AnimatedRoutes />
      </Layout>
    </ChartProvider>
  );
}

export default App;
