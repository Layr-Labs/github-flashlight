import React from 'react';
import DependencyGraph from './DependencyGraph';
import analysisData from '../data/analysisData';

function ApplicationGraph({ searchQuery }) {
  return (
    <div>
      <h2 style={{ padding: '1rem 2rem 0' }}>Application Interaction Graph</h2>
      <DependencyGraph
        data={analysisData.applicationGraph}
        services={analysisData.components}
      />
    </div>
  );
}

export default ApplicationGraph;
