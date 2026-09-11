/**
 * Format agent response text for better display
 * Converts \n to <br>, formats markdown-style lists and bold text
 */
function formatResponseText(text) {
    if (!text) return '';
    
    console.log('🔧 formatResponseText input:', text.substring(0, 200));
    
    // Remove surrounding quotes if present
    text = text.replace(/^["']|["']$/g, '');
    
    // Convert escaped newlines to actual newlines
    // Handle both \\n (double-escaped) and \n (single-escaped)
    text = text.replace(/\\\\n/g, '\n').replace(/\\n/g, '\n');
    
    // Convert **bold** to <strong>
    text = text.replace(/\*\*([^*]+)\*\*|__([^_]+)__/g, '<strong>$1$2</strong>');
    
    // Split into lines
    const lines = text.split('\n');
    const formatted = [];
    let inList = false;
    
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();
        
        if (!line) {
            // Empty line - close list if open, add paragraph break
            if (inList) {
                formatted.push('</ul>');
                inList = false;
            }
            formatted.push('<br>');
            continue;
        }
        
        // Check if line is a numbered list item (1. 2. 3. etc)
        const numberedMatch = line.match(/^(\d+)\.\s+(.+)$/);
        if (numberedMatch) {
            if (!inList) {
                formatted.push('<ol>');
                inList = 'ol';
            } else if (inList === 'ul') {
                formatted.push('</ul><ol>');
                inList = 'ol';
            }
            formatted.push(`<li>${numberedMatch[2]}</li>`);
            continue;
        }
        
        // Check if line is a bullet point (- or *)
        const bulletMatch = line.match(/^[-*]\s+(.+)$/);
        if (bulletMatch) {
            if (!inList) {
                formatted.push('<ul>');
                inList = 'ul';
            } else if (inList === 'ol') {
                formatted.push('</ol><ul>');
                inList = 'ul';
            }
            formatted.push(`<li>${bulletMatch[1]}</li>`);
            continue;
        }
        
        // Regular line
        if (inList) {
            formatted.push(inList === 'ul' ? '</ul>' : '</ol>');
            inList = false;
        }
        formatted.push(line + '<br>');
    }
    
    // Close any open list
    if (inList) {
        formatted.push(inList === 'ul' ? '</ul>' : '</ol>');
    }
    
    return formatted.join('\n');
}

// Make function available globally
window.formatResponseText = formatResponseText;
