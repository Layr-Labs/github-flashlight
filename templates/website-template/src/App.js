import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Header from './components/Header';
import ArchitectureOverview from './components/ArchitectureOverview';
import ComponentList from './components/ComponentList';
import ComponentDetail from './components/ComponentDetail';
import SwaggerUI from './components/SwaggerUI';
import analysisData from './data/analysisData';

function App() {
  return (
    <Router>
      <div className="App">
        <Header />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<ArchitectureOverview data={analysisData} />} />
            <Route path="/components" element={<ComponentList components={analysisData.services} />} />
            <Route path="/components/:componentName" element={<ComponentDetail components={analysisData.services} />} />
            <Route path="/components/:componentName/api" element={<SwaggerUI components={analysisData.services} />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
