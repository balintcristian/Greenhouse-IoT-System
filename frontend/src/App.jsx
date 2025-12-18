import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import HumidityForm from "./Components/HumidityForm/HumidityForm";
import MoistureForm from "./Components/MoistureForm/MoistureForm";
import TemperatureForm from "./Components/TemperatureForm/TemperatureForm";
import Header from "./Header";
// import Header from "./Header";
// import Footer from "./Footer";

function App() {
  const apiEndpoint = "http://cbuni.go.ro:8000";
  return (
    <Router>
      {/* <Header /> */}
      <Routes>
        <Route path="/humidity" element={<HumidityForm APIEndpoint={apiEndpoint} />} />
        <Route path="/moisture" element={<MoistureForm APIEndpoint={apiEndpoint} />} />
        <Route path="/temperature" element={<TemperatureForm APIEndpoint={apiEndpoint} />} />
        <Route path="*" element={<Header />} />
      </Routes>
      {/* <Footer /> */}
    </Router>
  );
}

export default App;
