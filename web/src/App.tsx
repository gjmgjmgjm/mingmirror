import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import { ChartProvider } from "./contexts/ChartContext";
import Dashboard from "./pages/Dashboard";
import Chart from "./pages/Chart";
import Council from "./pages/Council";
import Sandbox from "./pages/Sandbox";
import Calendar from "./pages/Calendar";
import Qizheng from "./pages/Qizheng";
import QizhengYearly from "./pages/QizhengYearly";
import Script from "./pages/Script";

function App() {
  return (
    <ChartProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/chart" element={<Chart />} />
          <Route path="/chart/yearly" element={<Chart />} />
          <Route path="/qizheng" element={<Qizheng />} />
          <Route path="/qizheng/yearly" element={<QizhengYearly />} />
          <Route path="/council" element={<Council />} />
          <Route path="/sandbox" element={<Sandbox />} />
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/script" element={<Script />} />
        </Routes>
      </Layout>
    </ChartProvider>
  );
}

export default App;
