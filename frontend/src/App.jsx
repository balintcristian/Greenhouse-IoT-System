import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import HumidityForm from "./Components/HumidityForm/HumidityForm";
import MoistureForm from "./Components/MoistureForm/MoistureForm";
import TemperatureForm from "./Components/TemperatureForm/TemperatureForm";
import Header from "./Header";
// import Header from "./Header";
// import Footer from "./Footer";

function App() {
  const apiEndpoint = "https://crispy.tplinkdns.com";
  return (
    <Router>
      {/* <Header /> */}
      <Routes>
        <Route path="*" element={<Header />} />
        <Route path="/humidity" element={<HumidityForm APIEndpoint={apiEndpoint} />} />
        <Route path="/moisture" element={<MoistureForm APIEndpoint={apiEndpoint} />} />
        <Route path="/temperature" element={<TemperatureForm APIEndpoint={apiEndpoint} />} />
      </Routes>
      {/* <Footer /> */}
    </Router>
  );
}

export default App;
