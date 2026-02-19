/**
 * Architecture summary markdown derived from analysisData.
 *
 * Provides the full architecture.md content used by Dashboard
 * for the system overview sections.
 *
 * DO NOT EDIT - this re-exports from analysisData.js
 */

import analysisData from './analysisData';

const summaryMarkdown = analysisData.architecture?.markdownContent || '';

export default summaryMarkdown;
