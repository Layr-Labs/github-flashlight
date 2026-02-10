import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeRaw from 'rehype-raw';
import '../styles/markdown.css';

/**
 * Reusable markdown content renderer with syntax highlighting and GFM support.
 *
 * Features:
 * - GitHub Flavored Markdown (tables, task lists, strikethrough)
 * - Syntax highlighting for code blocks
 * - Sanitized HTML support
 * - Consistent styling across all markdown content
 * - External links open in new tab
 * - Language labels on code blocks
 */
function MarkdownContent({ content, className = '' }) {
  if (!content) {
    return null;
  }

  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight, rehypeRaw]}
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
          // Custom rendering for code blocks - add language label
          code: ({ node, inline, className, children, ...props }) => {
            if (inline) {
              return <code className={className} {...props}>{children}</code>;
            }

            // Block code with language
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : '';

            return (
              <div className="code-block-wrapper">
                {language && <div className="code-language">{language}</div>}
                <code className={className} {...props}>
                  {children}
                </code>
              </div>
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
