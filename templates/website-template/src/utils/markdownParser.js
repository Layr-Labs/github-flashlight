// Shared markdown parsing utilities — used by Dashboard.js and ComponentDetails.js

export function parseSubsections(content) {
  const subsections = [];
  const lines = content.split('\n');
  let currentSubsection = null;
  let currentContent = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith('### ')) {
      if (currentSubsection) {
        subsections.push({ title: currentSubsection, content: currentContent.join('\n').trim() });
      }
      currentSubsection = line.substring(4).trim();
      currentContent = [];
    } else if (currentSubsection) {
      currentContent.push(line);
    }
  }

  if (currentSubsection) {
    subsections.push({ title: currentSubsection, content: currentContent.join('\n').trim() });
  }

  return subsections;
}

export function parseMarkdownSections(markdown) {
  if (!markdown) return [];

  markdown = markdown.replace(/\\`/g, '`');

  const sections = [];
  const lines = markdown.split('\n');
  let currentSection = null;
  let currentContent = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith('## ')) {
      if (currentSection) {
        const content = currentContent.join('\n').trim();
        sections.push({ title: currentSection, content, subsections: parseSubsections(content) });
      }
      currentSection = line.substring(3).trim();
      currentContent = [];
    } else if (currentSection) {
      currentContent.push(line);
    }
  }

  if (currentSection) {
    const content = currentContent.join('\n').trim();
    sections.push({ title: currentSection, content, subsections: parseSubsections(content) });
  }

  return sections;
}
