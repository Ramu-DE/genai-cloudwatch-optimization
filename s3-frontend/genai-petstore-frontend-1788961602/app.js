// Enhanced GenAI Petstore Application
// Task 19: Enhanced Frontend Visual Design and User Experience

class EnhancedPetstoreApp {
    constructor() {
        this.currentUser = null;
        this.petProfile = {};
        this.appointments = [];
        this.serviceHistory = [];
        this.isLoading = false;
        this.stockUpdateInterval = null;
        this.init();
    }

    init() {
        this.loadUserData();
        this.initializeEventListeners();
        this.startStockUpdates();
        this.initializeAnimations();
        this.loadAppointments();
        this.loadServiceHistory();
    }

    loadUserData() {
        // Load actual authenticated user data from session storage
        try {
            const userData = sessionStorage.getItem('userData');
            if (userData) {
                this.currentUser = JSON.parse(userData);
                console.log('✅ Loaded user data:', this.currentUser);
            } else {
                // Fallback to simulated data if no session data
                console.warn('⚠️ No session data found, using fallback');
                this.currentUser = {
                    name: "Pet Parent",
                    email: "parent@example.com",
                    customerId: "cust_demo",
                    preferences: {
                        notifications: true,
                        theme: "light"
                    }
                };
            }
        } catch (error) {
            console.error('❌ Error loading user data:', error);
            // Fallback data
            this.currentUser = {
                name: "Pet Parent", 
                email: "parent@example.com",
                customerId: "cust_demo",
                preferences: {
                    notifications: true,
                    theme: "light"
                }
            };
        }

        // Update UI with user info
        const userNameElement = document.getElementById('user-name');
        if (userNameElement) {
            userNameElement.textContent = `Welcome, ${this.currentUser.name}!`;
        }
    }

    initializeEventListeners() {
        // Enhanced form submissions
        document.addEventListener('submit', (e) => {
            if (e.target.id === 'pet-profile-form') {
                this.handlePetProfileSubmission(e);
            }
        });

        // Enhanced navigation
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('nav-link')) {
                this.handleNavigation(e);
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            this.handleKeyboardShortcuts(e);
        });

        // Intersection Observer for animations
        this.setupIntersectionObserver();
    }

    handleNavigation(e) {
        e.preventDefault();
        const targetSection = e.target.getAttribute('onclick');
        if (targetSection) {
            const sectionName = targetSection.match(/showSection\('(.+)'\)/)?.[1];
            if (sectionName) {
                this.showSection(sectionName);
                this.addNavigationAnimation(e.target);
            }
        }
    }

    addNavigationAnimation(element) {
        element.classList.add('pulse');
        setTimeout(() => {
            element.classList.remove('pulse');
        }, 600);
    }

    handleKeyboardShortcuts(e) {
        // Ctrl/Cmd + number keys for quick navigation
        if ((e.ctrlKey || e.metaKey) && e.key >= '1' && e.key <= '6') {
            e.preventDefault();
            const sections = ['agents', 'profile', 'appointments', 'history', 'ai-features', 'products'];
            const sectionIndex = parseInt(e.key) - 1;
            if (sections[sectionIndex]) {
                this.showSection(sections[sectionIndex]);
            }
        }

        // Escape key to close modals/chats
        if (e.key === 'Escape') {
            this.closeActiveModals();
        }
    }

    closeActiveModals() {
        const chatInterface = document.getElementById('chat-interface');
        if (chatInterface && chatInterface.style.display !== 'none') {
            this.endChat();
        }
    }

    setupIntersectionObserver() {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('animate-in');
                }
            });
        }, {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        });

        // Observe all cards and sections
        document.querySelectorAll('.enhanced-card, .agent-card, .product-card-enhanced').forEach(el => {
            observer.observe(el);
        });
    }

    initializeAnimations() {
        // Add CSS for intersection observer animations
        const style = document.createElement('style');
        style.textContent = `
            .animate-in {
                animation: slideInFromBottom 0.6s ease-out forwards;
            }
            
            @keyframes slideInFromBottom {
                from {
                    opacity: 0;
                    transform: translateY(30px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
        `;
        document.head.appendChild(style);
    }

    startStockUpdates() {
        // Real-time stock update simulation
        this.stockUpdateInterval = setInterval(() => {
            this.updateStockLevels();
        }, 10000); // Update every 10 seconds
    }

    updateStockLevels() {
        const stockItems = document.querySelectorAll('.stock-item');
        stockItems.forEach(item => {
            const stockCount = item.querySelector('.stock-count');
            const stockFill = item.querySelector('.stock-fill');

            if (stockCount && stockFill) {
                const currentCount = parseInt(stockCount.textContent.match(/\d+/)?.[0] || 0);
                const change = Math.floor(Math.random() * 3) - 1; // -1, 0, or 1
                const newCount = Math.max(0, Math.min(50, currentCount + change));

                if (newCount !== currentCount) {
                    this.animateStockChange(stockCount, stockFill, newCount);
                }
            }
        });
    }

    animateStockChange(countElement, fillElement, newCount) {
        // Animate the number change
        countElement.style.transform = 'scale(1.2)';
        countElement.style.color = 'var(--primary-sage)';

        setTimeout(() => {
            countElement.textContent = `${newCount} left`;
            countElement.style.transform = 'scale(1)';
            countElement.style.color = '';
        }, 200);

        // Update the progress bar
        let percentage, className;
        if (newCount > 20) {
            percentage = Math.min(100, (newCount / 30) * 100);
            className = 'high';
        } else if (newCount > 5) {
            percentage = (newCount / 20) * 60;
            className = 'medium';
        } else {
            percentage = (newCount / 5) * 30;
            className = 'low';
        }

        fillElement.style.width = `${percentage}%`;
        fillElement.className = `stock-fill ${className}`;

        // Add pulse animation
        fillElement.classList.add('stock-update-animation');
        setTimeout(() => {
            fillElement.classList.remove('stock-update-animation');
        }, 2000);
    }

    handlePetProfileSubmission(e) {
        e.preventDefault();
        const formData = new FormData(e.target);

        // Extract form data
        this.petProfile = {
            name: formData.get('pet-name') || document.getElementById('pet-name')?.value,
            species: formData.get('pet-species') || document.getElementById('pet-species')?.value,
            breed: formData.get('pet-breed') || document.getElementById('pet-breed')?.value,
            age: formData.get('pet-age') || document.getElementById('pet-age')?.value,
            weight: formData.get('pet-weight') || document.getElementById('pet-weight')?.value,
            gender: formData.get('pet-gender') || document.getElementById('pet-gender')?.value,
            specialNeeds: formData.get('pet-special-needs') || document.getElementById('pet-special-needs')?.value,
            behavior: formData.get('pet-behavior') || document.getElementById('pet-behavior')?.value
        };

        this.savePetProfile();
    }

    savePetProfile() {
        const submitBtn = document.querySelector('#pet-profile-form button[type="submit"]');
        const originalText = submitBtn.textContent;

        // Show loading state
        submitBtn.textContent = 'Saving...';
        submitBtn.disabled = true;
        submitBtn.classList.add('loading');

        // Simulate API call
        setTimeout(() => {
            // Success state
            submitBtn.textContent = '✅ Profile Saved!';
            submitBtn.classList.remove('loading');
            submitBtn.classList.add('success');

            // Show success message
            this.showNotification('Pet profile saved successfully!', 'success');

            // Reset button after delay
            setTimeout(() => {
                submitBtn.textContent = originalText;
                submitBtn.disabled = false;
                submitBtn.classList.remove('success');
            }, 2000);
        }, 1500);
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <span>${message}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="notification-close">×</button>
            </div>
        `;

        // Add notification styles if not already present
        if (!document.querySelector('#notification-styles')) {
            const style = document.createElement('style');
            style.id = 'notification-styles';
            style.textContent = `
                .notification {
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    background: white;
                    border-radius: var(--radius-md);
                    box-shadow: var(--shadow-lg);
                    z-index: 1000;
                    transform: translateX(100%);
                    transition: transform var(--transition-normal);
                    min-width: 300px;
                }
                
                .notification.show {
                    transform: translateX(0);
                }
                
                .notification-success {
                    border-left: 4px solid var(--success);
                }
                
                .notification-error {
                    border-left: 4px solid var(--error);
                }
                
                .notification-info {
                    border-left: 4px solid var(--primary-sage);
                }
                
                .notification-content {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: var(--spacing-md);
                }
                
                .notification-close {
                    background: none;
                    border: none;
                    font-size: 1.2rem;
                    cursor: pointer;
                    color: #666;
                }
            `;
            document.head.appendChild(style);
        }

        document.body.appendChild(notification);

        // Trigger animation
        setTimeout(() => {
            notification.classList.add('show');
        }, 100);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.remove();
                }
            }, 300);
        }, 5000);
    }

    loadAppointments() {
        const appointmentsContainer = document.getElementById('appointments-list');
        if (!appointmentsContainer) return;

        // Show loading state
        this.showLoadingState('appointments-loading');

        // Simulate API call
        setTimeout(() => {
            this.appointments = [
                {
                    id: 1,
                    agentName: 'Bella',
                    service: 'Grooming Session',
                    date: '2024-01-15',
                    time: '10:00 AM',
                    status: 'scheduled',
                    petName: 'Max'
                },
                {
                    id: 2,
                    agentName: 'Oliver',
                    service: 'Health Checkup',
                    date: '2024-01-18',
                    time: '2:30 PM',
                    status: 'scheduled',
                    petName: 'Max'
                },
                {
                    id: 3,
                    agentName: 'Luna',
                    service: 'Nutrition Consultation',
                    date: '2024-01-12',
                    time: '11:00 AM',
                    status: 'completed',
                    petName: 'Max'
                }
            ];

            this.renderAppointments();
            this.hideLoadingState('appointments-loading');
        }, 1000);
    }

    renderAppointments() {
        const container = document.getElementById('appointments-list');
        if (!container) return;

        if (this.appointments.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <h3>No appointments scheduled</h3>
                    <p>Book your first appointment with one of our AI specialists!</p>
                    <button class="btn btn-primary" onclick="showSection('agents')">Book Appointment</button>
                </div>
            `;
            return;
        }

        container.innerHTML = this.appointments.map(appointment => `
            <div class="appointment-item" data-id="${appointment.id}">
                <div class="appointment-info">
                    <h4>${appointment.service} with ${appointment.agentName}</h4>
                    <p><strong>Pet:</strong> ${appointment.petName}</p>
                    <p><strong>Date:</strong> ${appointment.date} at ${appointment.time}</p>
                </div>
                <div class="appointment-actions">
                    <span class="appointment-status status-${appointment.status}">
                        ${appointment.status.charAt(0).toUpperCase() + appointment.status.slice(1)}
                    </span>
                    ${appointment.status === 'scheduled' ? `
                        <button class="btn btn-secondary btn-sm" onclick="app.rescheduleAppointment(${appointment.id})">
                            Reschedule
                        </button>
                        <button class="btn btn-accent btn-sm" onclick="app.cancelAppointment(${appointment.id})">
                            Cancel
                        </button>
                    ` : ''}
                </div>
            </div>
        `).join('');
    }

    loadServiceHistory() {
        const historyContainer = document.getElementById('history-list');
        if (!historyContainer) return;

        // Show loading state
        this.showLoadingState('history-loading');

        // Simulate API call
        setTimeout(() => {
            this.serviceHistory = [
                {
                    id: 1,
                    agentName: 'Bella',
                    service: 'Full Grooming Package',
                    date: '2023-12-20',
                    rating: 5,
                    notes: 'Excellent service! Max looks amazing.'
                },
                {
                    id: 2,
                    agentName: 'Oliver',
                    service: 'Annual Checkup',
                    date: '2023-11-15',
                    rating: 5,
                    notes: 'Thorough examination. Very professional.'
                },
                {
                    id: 3,
                    agentName: 'Max',
                    service: 'Basic Training Session',
                    date: '2023-10-10',
                    rating: 4,
                    notes: 'Great progress on sit and stay commands.'
                }
            ];

            this.renderServiceHistory();
            this.hideLoadingState('history-loading');
        }, 800);
    }

    renderServiceHistory() {
        const container = document.getElementById('history-list');
        if (!container) return;

        if (this.serviceHistory.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <h3>No service history</h3>
                    <p>Your completed appointments will appear here.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = this.serviceHistory.map(service => `
            <div class="appointment-item history-item" data-id="${service.id}">
                <div class="appointment-info">
                    <h4>${service.service} with ${service.agentName}</h4>
                    <p><strong>Date:</strong> ${service.date}</p>
                    <p><strong>Rating:</strong> ${'★'.repeat(service.rating)}${'☆'.repeat(5 - service.rating)}</p>
                    <p><strong>Notes:</strong> ${service.notes}</p>
                </div>
                <div class="appointment-actions">
                    <button class="btn btn-primary btn-sm" onclick="app.bookAgain('${service.agentName.toLowerCase()}')">
                        Book Again
                    </button>
                    <button class="btn btn-secondary btn-sm" onclick="app.leaveReview(${service.id})">
                        Update Review
                    </button>
                </div>
            </div>
        `).join('');
    }

    showLoadingState(elementId) {
        const element = document.getElementById(elementId);
        if (element) {
            element.style.display = 'flex';
        }
    }

    hideLoadingState(elementId) {
        const element = document.getElementById(elementId);
        if (element) {
            element.style.display = 'none';
        }
    }

    rescheduleAppointment(appointmentId) {
        const appointment = this.appointments.find(a => a.id === appointmentId);
        if (appointment) {
            const newDate = prompt('Enter new date (YYYY-MM-DD):', appointment.date);
            const newTime = prompt('Enter new time:', appointment.time);

            if (newDate && newTime) {
                appointment.date = newDate;
                appointment.time = newTime;
                this.renderAppointments();
                this.showNotification('Appointment rescheduled successfully!', 'success');
            }
        }
    }

    cancelAppointment(appointmentId) {
        if (confirm('Are you sure you want to cancel this appointment?')) {
            this.appointments = this.appointments.filter(a => a.id !== appointmentId);
            this.renderAppointments();
            this.showNotification('Appointment cancelled successfully.', 'info');
        }
    }

    bookAgain(agentType) {
        // Navigate to agents section and highlight the specific agent
        this.showSection('agents');

        setTimeout(() => {
            const agentCards = document.querySelectorAll('.agent-card');
            agentCards.forEach(card => {
                const agentName = card.querySelector('.agent-name')?.textContent.toLowerCase();
                if (agentName === agentType) {
                    card.classList.add('highlight');
                    card.scrollIntoView({ behavior: 'smooth', block: 'center' });

                    setTimeout(() => {
                        card.classList.remove('highlight');
                    }, 3000);
                }
            });
        }, 500);
    }

    leaveReview(serviceId) {
        const service = this.serviceHistory.find(s => s.id === serviceId);
        if (service) {
            const rating = prompt('Rate this service (1-5 stars):', service.rating);
            const notes = prompt('Update your review:', service.notes);

            if (rating && notes) {
                service.rating = Math.max(1, Math.min(5, parseInt(rating)));
                service.notes = notes;
                this.renderServiceHistory();
                this.showNotification('Review updated successfully!', 'success');
            }
        }
    }

    showSection(sectionName) {
        const sections = document.querySelectorAll('.section');
        const navLinks = document.querySelectorAll('.nav-link');

        sections.forEach(section => {
            section.classList.remove('active');
        });

        navLinks.forEach(link => {
            link.classList.remove('active');
        });

        const targetSection = document.getElementById(`${sectionName}-section`);
        if (targetSection) {
            targetSection.classList.add('active');
            targetSection.classList.add('slide-in-bottom');
        }

        // Update active nav link
        const activeLink = document.querySelector(`[onclick="showSection('${sectionName}')"]`);
        if (activeLink) {
            activeLink.classList.add('active');
        }
    }

    destroy() {
        // Clean up intervals and event listeners
        if (this.stockUpdateInterval) {
            clearInterval(this.stockUpdateInterval);
        }
    }
}

// Initialize the enhanced app
let app;
document.addEventListener('DOMContentLoaded', function () {
    app = new EnhancedPetstoreApp();

    // Add highlight animation styles
    const style = document.createElement('style');
    style.textContent = `
        .highlight {
            animation: highlightPulse 3s ease-in-out;
            border: 2px solid var(--primary-sage) !important;
        }
        
        @keyframes highlightPulse {
            0%, 100% { 
                box-shadow: 0 0 0 0 rgba(168, 198, 159, 0.7);
            }
            50% { 
                box-shadow: 0 0 0 20px rgba(168, 198, 159, 0);
            }
        }
        
        .loading {
            position: relative;
            overflow: hidden;
        }
        
        .loading::after {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
            animation: loading-shimmer 1.5s infinite;
        }
        
        @keyframes loading-shimmer {
            0% { left: -100%; }
            100% { left: 100%; }
        }
        
        .success {
            background: var(--success) !important;
            color: white !important;
        }
    `;
    document.head.appendChild(style);
});

// Global navigation functions
function showSection(sectionName) {
    if (window.app) {
        window.app.showSection(sectionName);
    }
}

function logout() {
    if (confirm('Are you sure you want to logout?')) {
        // Clear session data
        sessionStorage.clear();
        localStorage.clear();
        
        // Redirect to auth page
        window.location.href = '/auth.html';
    }
}

function savePetProfile(event) {
    if (window.app) {
        window.app.handlePetProfileSubmission(event);
    }
}

// AI Features functions
function showAITool(toolName) {
    console.log(`Showing AI tool: ${toolName}`);
    
    const tools = ['matcher', 'tryon', 'sizing', 'recommendations'];
    
    // Hide all tools
    tools.forEach(tool => {
        const element = document.getElementById(`ai-${tool === 'recommendations' ? 'personalized-recommendations' : tool === 'matcher' ? 'product-matcher' : tool === 'tryon' ? 'virtual-tryon' : 'smart-size-guide'}`);
        if (element) {
            element.style.display = 'none';
        }
    });
    
    // Show selected tool
    const targetId = toolName === 'recommendations' ? 'ai-personalized-recommendations' : 
                    toolName === 'matcher' ? 'ai-product-matcher' : 
                    toolName === 'tryon' ? 'virtual-tryon' : 
                    'smart-size-guide';
    
    const targetElement = document.getElementById(targetId);
    if (targetElement) {
        targetElement.style.display = 'block';
        targetElement.innerHTML = `
            <div style="background: white; padding: 30px; border-radius: 15px; box-shadow: 0 8px 25px rgba(0,0,0,0.1); margin-top: 20px;">
                <h3>🚀 ${toolName.charAt(0).toUpperCase() + toolName.slice(1)} Tool</h3>
                <p>This AI-powered tool is coming soon! We're working on bringing you the best ${toolName} experience.</p>
                <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h4>What this tool will do:</h4>
                    <ul style="margin: 10px 0; padding-left: 20px;">
                        ${toolName === 'matcher' ? `
                            <li>Analyze your pet's breed, age, and lifestyle</li>
                            <li>Match products from thousands of options</li>
                            <li>Provide personalized recommendations</li>
                            <li>Consider health conditions and preferences</li>
                        ` : toolName === 'tryon' ? `
                            <li>Use AR technology for virtual fitting</li>
                            <li>See how accessories look on your pet</li>
                            <li>Try different colors and styles</li>
                            <li>Ensure perfect fit before purchase</li>
                        ` : toolName === 'sizing' ? `
                            <li>AI-powered size recommendations</li>
                            <li>Based on breed and measurements</li>
                            <li>Prevent ordering wrong sizes</li>
                            <li>Size conversion across brands</li>
                        ` : `
                            <li>Machine learning recommendations</li>
                            <li>Based on pet's unique needs</li>
                            <li>Health condition considerations</li>
                            <li>Behavioral pattern analysis</li>
                        `}
                    </ul>
                </div>
                <button class="btn btn-secondary" onclick="this.parentElement.parentElement.style.display='none'">Close</button>
            </div>
        `;
        
        // Scroll to the tool
        targetElement.scrollIntoView({ behavior: 'smooth' });
    }
}

// Export for global access
window.EnhancedPetstoreApp = EnhancedPetstoreApp;