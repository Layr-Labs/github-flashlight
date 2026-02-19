/**
 * Component markdown content map derived from analysisData.
 *
 * Provides a { componentName: markdownString } lookup used by ComponentDetails
 * to render full documentation for each component.
 *
 * DO NOT EDIT - this re-exports from analysisData.js
 */

import analysisData from './analysisData';

const markdownContent = {};
for (const component of analysisData.components) {
  markdownContent[component.name] = component.markdownContent || '';
}

export default markdownContent;
