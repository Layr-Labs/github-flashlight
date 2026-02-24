import React from 'react';
import DependencyGraph from './DependencyGraph';
import analysisData from '../data/analysisData';

function LibraryGraph() {
  return (
    <div>
      <h2 style={{ padding: '1rem 2rem 0' }}>Library Dependency Graph</h2>
      <DependencyGraph
        data={analysisData.libraryGraph}
        services={analysisData.components}
      />
    </div>
  );
}

export default LibraryGraph;
