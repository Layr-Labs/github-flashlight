import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Header from './components/Header';
import SearchModal from './components/SearchModal';
import LibraryGraph from './components/LibraryGraph';
import ApplicationGraph from './components/ApplicationGraph';
import ComponentList from './components/ComponentList';
import ComponentDetails from './components/ComponentDetails';
import Dashboard from './components/Dashboard';
import analysisData from './data/analysisData';
import './styles/App.css';

function App() {
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  return (
    <Router>
      <div className="App">
        <Header onSearchToggle={() => setIsSearchOpen(true)} />

        <main className="app-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/components" element={<ComponentList components={analysisData.components} />} />
            <Route path="/library-graph" element={<LibraryGraph />} />
            <Route path="/application-graph" element={<ApplicationGraph />} />
            <Route path="/:componentName" element={<ComponentDetails />} />
          </Routes>
        </main>

        <SearchModal
          isOpen={isSearchOpen}
          onClose={() => setIsSearchOpen(false)}
          components={analysisData.components}
        />
      </div>
    </Router>
  );
}

export default App;
