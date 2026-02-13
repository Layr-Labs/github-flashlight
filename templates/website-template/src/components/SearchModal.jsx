import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import './SearchModal.css';

function SearchModal({ isOpen, onClose, components = [] }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef(null);
  const navigate = useNavigate();

  // Filter components based on search term
  const filteredComponents = components.filter(component => {
    const term = searchTerm.toLowerCase();
    return (
      component.name.toLowerCase().includes(term) ||
      (component.description && component.description.toLowerCase().includes(term)) ||
      (component.type && component.type.toLowerCase().includes(term)) ||
      (component.classification && component.classification.toLowerCase().includes(term))
    );
  }).slice(0, 10); // Limit to 10 results

  // Reset selection when search term changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [searchTerm]);

  // Focus input when modal opens
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
      setSearchTerm('');
      setSelectedIndex(0);
    }
  }, [isOpen]);

  // Handle keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isOpen) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => Math.min(prev + 1, filteredComponents.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => Math.max(prev - 1, 0));
      } else if (e.key === 'Enter' && filteredComponents.length > 0) {
        e.preventDefault();
        handleSelect(filteredComponents[selectedIndex]);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, selectedIndex, filteredComponents, onClose]);

  const handleSelect = (component) => {
    navigate(`/components/${component.name}`);
    onClose();
  };

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="search-modal-backdrop" onClick={handleBackdropClick}>
      <div className="search-modal">
        <div className="search-input-container">
          <span className="search-icon">🔍</span>
          <input
            ref={inputRef}
            type="text"
            className="search-modal-input"
            placeholder="Search components..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
          <kbd className="search-shortcut">ESC</kbd>
        </div>

        <div className="search-results">
          {searchTerm === '' ? (
            <div className="search-hint">
              <p>💡 Start typing to search across all components</p>
              <div className="search-tips">
                <span>• Search by name, description, or type</span>
                <span>• Use ↑↓ arrows to navigate</span>
                <span>• Press Enter to open</span>
              </div>
            </div>
          ) : filteredComponents.length === 0 ? (
            <div className="no-results">
              <span className="no-results-icon">🔍</span>
              <p>No components found for "{searchTerm}"</p>
            </div>
          ) : (
            <ul className="results-list">
              {filteredComponents.map((component, index) => (
                <li
                  key={component.name}
                  className={`result-item ${index === selectedIndex ? 'selected' : ''}`}
                  onClick={() => handleSelect(component)}
                  onMouseEnter={() => setSelectedIndex(index)}
                >
                  <div className="result-icon">
                    {component.classification === 'application' ? '🚀' : '📚'}
                  </div>
                  <div className="result-content">
                    <div className="result-name">{component.name}</div>
                    <div className="result-meta">
                      <span className={`result-badge ${component.classification}`}>
                        {component.classification}
                      </span>
                      {component.type && (
                        <span className="result-type">{component.type}</span>
                      )}
                    </div>
                  </div>
                  {index === selectedIndex && (
                    <kbd className="result-enter">↵</kbd>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="search-footer">
          <div className="search-footer-shortcuts">
            <span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span>
            <span><kbd>↵</kbd> Select</span>
            <span><kbd>ESC</kbd> Close</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SearchModal;
