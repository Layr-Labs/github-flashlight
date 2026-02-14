import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import hljs from 'highlight.js';
import MermaidDiagram from './MermaidDiagram';
import '../styles/markdown.css';
import 'highlight.js/styles/github-dark.css';

/**
 * Reusable markdown content renderer with syntax highlighting and GFM support.
 *
 * Features:
 * - GitHub Flavored Markdown (tables, task lists, strikethrough)
 * - Syntax highlighting for code blocks using highlight.js
 * - Mermaid diagram support
 * - Consistent styling across all markdown content
 * - External links open in new tab
 */
function MarkdownContent({ content, className = '' }) {
  if (!content) {
    return null;
  }

  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Custom rendering for links - open external links in new tab
          a: ({ node, href, children, ...props }) => {
            const isExternal = href?.startsWith('http');
            return (
              <a
                href={href}
                target={isExternal ? '_blank' : undefined}
                rel={isExternal ? 'noopener noreferrer' : undefined}
                {...props}
              >
                {children}
              </a>
            );
          },
          // Custom rendering for code blocks with syntax highlighting
          code: ({ node, inline, className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : '';
            const codeString = String(children).replace(/\n$/, '');

            // Handle mermaid diagrams
            if (!inline && language === 'mermaid') {
              return <MermaidDiagram chart={codeString} />;
            }

            // Handle code blocks with syntax highlighting
            if (!inline && language) {
              try {
                const highlighted = hljs.highlight(codeString, {
                  language: language,
                  ignoreIllegals: true
                });
                return (
                  <code
                    className={`${className} hljs`}
                    dangerouslySetInnerHTML={{ __html: highlighted.value }}
                    {...props}
                  />
                );
              } catch (e) {
                // Fallback if language not supported
                return (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              }
            }

            // Inline code
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default MarkdownContent;
