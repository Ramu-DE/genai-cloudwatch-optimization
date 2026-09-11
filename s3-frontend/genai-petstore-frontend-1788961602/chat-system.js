// Configuration loaded from config.js
// Ensure config.js is included before this file

// Enhanced Chat System with Pet Display from DynamoDB
// Shows user's pets and aligns agent responses with actual data

class ChatSystem {
    constructor() {
        this.currentAgent = null;
        this.sessionId = null;
        this.isLoading = false;
        this.currentCustomer = null;
        this.customerPets = [];
        // API Gateway URL for agent communication
        this.apiUrl = window.PETSTORE_CONFIG?.API_ENDPOINT || window.CONFIG?.AGENTS_ENDPOINT;
        // API Gateway URL for DynamoDB data access
        this.dataApiUrl = window.PETSTORE_CONFIG?.API_ENDPOINT || window.CONFIG?.AGENTS_ENDPOINT;
        this.agentArns = {
            'bella': window.PETSTORE_CONFIG?.AGENT_ARNS?.bella || '',
            'oliver': window.PETSTORE_CONFIG?.AGENT_ARNS?.oliver || '',
            'luna': window.PETSTORE_CONFIG?.AGENT_ARNS?.luna || '',
            'max': window.PETSTORE_CONFIG?.AGENT_ARNS?.max || '',
            'patrick': window.PETSTORE_CONFIG?.AGENT_ARNS?.patrick || ''
        };
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.createChatModal();
        this.createPetDisplayModal();
        this.loadCustomerData();
        this.fixUIIssues();
    }

    async loadCustomerData() {
        """Load customer and pet data from DynamoDB"""
        try {
            console.log('🔍 Loading customer data from DynamoDB...');
            
            // Get customer data via Lambda/DynamoDB
            const response = await fetch(this.dataApiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Origin': window.PETSTORE_CONFIG.API_ENDPOINT
                },
                body: JSON.stringify({
                    agentArn: this.agentArns['bella'], // Use any agent to get customer data
                    message: 'Get my customer profile and pets',
                    sessionId: `data-session-${Date.now()}`,
                    userId: 'sarah'
                })
            });

            if (response.ok) {
                const result = await response.json();
                console.log('📥 Customer data response:', result);
                
                // Parse customer and pet information from response
                this.parseCustomerData(result.response);
                this.displayCustomerPets();
            } else {
                console.warn('⚠️ Could not load customer data');
            }
        } catch (error) {
            console.error('❌ Error loading customer data:', error);
        }
    }

    parseCustomerData(responseText) {
        """Parse customer and pet data from agent response"""
        try {
            // Extract customer name
            const nameMatch = responseText.match(/Customer[^:]*:\s*([^\n]+)/i);
            if (nameMatch) {
                this.currentCustomer = nameMatch[1].trim();
                console.log('👤 Customer:', this.currentCustomer);
            }

            // Extract pet information
            const petMatches = responseText.match(/\d+\. ([^-]+) - ([^(]+)\(([^,]+), ([^,]+), ([^)]+)\)/g);
            if (petMatches) {
                this.customerPets = petMatches.map(match => {
                    const parts = match.match(/\d+\. ([^-]+) - ([^(]+)\(([^,]+), ([^,]+), ([^)]+)\)/);
                    if (parts) {
                        return {
                            name: parts[1].trim(),
                            breed: parts[2].trim(),
                            species: parts[3].trim(),
                            age: parts[4].trim(),
                            weight: parts[5].trim()
                        };
                    }
                    return null;
                }).filter(pet => pet !== null);
                
                console.log('🐾 Pets loaded:', this.customerPets);
            }
        } catch (error) {
            console.error('❌ Error parsing customer data:', error);
        }
    }

    displayCustomerPets() {
        """Display customer pets in the UI"""
        // Add pets display to the main interface
        const existingPetsDisplay = document.getElementById('customer-pets-display');
        if (existingPetsDisplay) {
            existingPetsDisplay.remove();
        }

        if (this.customerPets.length > 0) {
            const petsDisplay = document.createElement('div');
            petsDisplay.id = 'customer-pets-display';
            petsDisplay.className = 'customer-pets-display';
            
            let petsHtml = `
                <div class="pets-header">
                    <h3>👤 ${this.currentCustomer || 'Your'} Pets</h3>
                    <button class="pets-toggle" onclick="window.chatSystem.togglePetsDisplay()">
                        <span class="pets-count">${this.customerPets.length}</span>
                    </button>
                </div>
                <div class="pets-list" id="pets-list">
            `;
            
            this.customerPets.forEach((pet, index) => {
                const petIcon = pet.species.toLowerCase().includes('dog') ? '🐕' : 
                               pet.species.toLowerCase().includes('cat') ? '🐱' : '🐾';
                
                petsHtml += `
                    <div class="pet-card" data-pet-index="${index}">
                        <div class="pet-icon">${petIcon}</div>
                        <div class="pet-info">
                            <div class="pet-name">${pet.name}</div>
                            <div class="pet-details">${pet.breed} • ${pet.age} • ${pet.weight}</div>
                        </div>
                        <button class="pet-select-btn" onclick="window.chatSystem.selectPet(${index})">
                            Select
                        </button>
                    </div>
                `;
            });
            
            petsHtml += '</div>';
            petsDisplay.innerHTML = petsHtml;
            
            // Insert pets display at the top of the page
            const mainContent = document.querySelector('.hero-section') || document.body;
            mainContent.insertBefore(petsDisplay, mainContent.firstChild);
        }
    }

    createPetDisplayModal() {
        """Create modal for detailed pet information"""
        const modal = document.createElement('div');
        modal.id = 'pet-detail-modal';
        modal.className = 'pet-detail-modal';
        modal.innerHTML = `
            <div class="pet-detail-content">
                <div class="pet-detail-header">
                    <h3 id="pet-detail-name">Pet Details</h3>
                    <button class="close-pet-detail" onclick="window.chatSystem.closePetDetail()">✕</button>
                </div>
                <div class="pet-detail-body" id="pet-detail-body">
                    <!-- Pet details will be populated here -->
                </div>
                <div class="pet-detail-actions">
                    <button class="btn btn-primary" onclick="window.chatSystem.bookAppointmentForPet()">
                        Book Appointment
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    togglePetsDisplay() {
        """Toggle pets list visibility"""
        const petsList = document.getElementById('pets-list');
        if (petsList) {
            petsList.style.display = petsList.style.display === 'none' ? 'block' : 'none';
        }
    }

    selectPet(petIndex) {
        """Select a pet and show details"""
        if (petIndex >= 0 && petIndex < this.customerPets.length) {
            const pet = this.customerPets[petIndex];
            this.showPetDetail(pet);
        }
    }

    showPetDetail(pet) {
        """Show detailed pet information"""
        const modal = document.getElementById('pet-detail-modal');
        const nameElement = document.getElementById('pet-detail-name');
        const bodyElement = document.getElementById('pet-detail-body');
        
        nameElement.textContent = `${pet.name} - ${pet.breed}`;
        
        const petIcon = pet.species.toLowerCase().includes('dog') ? '🐕' : 
                       pet.species.toLowerCase().includes('cat') ? '🐱' : '🐾';
        
        bodyElement.innerHTML = `
            <div class="pet-detail-card">
                <div class="pet-detail-icon">${petIcon}</div>
                <div class="pet-detail-info">
                    <div class="pet-detail-row">
                        <span class="pet-detail-label">Name:</span>
                        <span class="pet-detail-value">${pet.name}</span>
                    </div>
                    <div class="pet-detail-row">
                        <span class="pet-detail-label">Breed:</span>
                        <span class="pet-detail-value">${pet.breed}</span>
                    </div>
                    <div class="pet-detail-row">
                        <span class="pet-detail-label">Species:</span>
                        <span class="pet-detail-value">${pet.species}</span>
                    </div>
                    <div class="pet-detail-row">
                        <span class="pet-detail-label">Age:</span>
                        <span class="pet-detail-value">${pet.age}</span>
                    </div>
                    <div class="pet-detail-row">
                        <span class="pet-detail-label">Weight:</span>
                        <span class="pet-detail-value">${pet.weight}</span>
                    </div>
                </div>
            </div>
            <div class="pet-services-suggestion">
                <h4>Recommended Services for ${pet.name}:</h4>
                <div class="service-suggestions">
                    <button class="service-suggestion-btn" onclick="window.chatSystem.startChatWithPet('bella', '${pet.name}')">
                        🐕 Grooming Services
                    </button>
                    <button class="service-suggestion-btn" onclick="window.chatSystem.startChatWithPet('oliver', '${pet.name}')">
                        🏥 Health Checkup
                    </button>
                    <button class="service-suggestion-btn" onclick="window.chatSystem.startChatWithPet('luna', '${pet.name}')">
                        🥗 Nutrition Plan
                    </button>
                    <button class="service-suggestion-btn" onclick="window.chatSystem.startChatWithPet('max', '${pet.name}')">
                        🎾 Training Program
                    </button>
                </div>
            </div>
        `;
        
        modal.classList.add('active');
    }

    closePetDetail() {
        """Close pet detail modal"""
        const modal = document.getElementById('pet-detail-modal');
        modal.classList.remove('active');
    }

    startChatWithPet(agentName, petName) {
        """Start chat with specific agent and pet context"""
        this.closePetDetail();
        
        // Find the pet data
        const pet = this.customerPets.find(p => p.name === petName);
        if (pet) {
            // Start chat with pet-specific context
            const petContext = `I'd like to discuss services for my ${pet.species.toLowerCase()} ${pet.name}, who is a ${pet.breed}, ${pet.age} old, weighing ${pet.weight}.`;
            this.startChatWithContext(agentName, petContext);
        } else {
            this.startChat(agentName);
        }
    }

    startChatWithContext(agentName, initialMessage) {
        """Start chat with specific context message"""
        this.startChat(agentName);
        
        // Wait for chat to initialize, then send context message
        setTimeout(() => {
            const input = document.getElementById('chat-input');
            if (input) {
                input.value = initialMessage;
                this.sendMessage();
            }
        }, 500);
    }

    // ... (rest of the existing chat system methods remain the same)
    
    fixUIIssues() {
        // Enhanced UI fixes including pet display styles
        const style = document.createElement('style');
        style.id = 'ui-fixes-enhanced';
        style.textContent = `
            /* Existing UI fixes... */
            
            /* Pet Display Styles */
            .customer-pets-display {
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                margin: 20px;
                padding: 20px;
                border: 2px solid var(--primary-sage);
            }
            
            .pets-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 15px;
            }
            
            .pets-header h3 {
                margin: 0;
                color: var(--neutral-charcoal);
                font-size: 1.2rem;
            }
            
            .pets-toggle {
                background: var(--primary-sage);
                color: white;
                border: none;
                border-radius: 20px;
                padding: 8px 16px;
                cursor: pointer;
                font-weight: 600;
                transition: all 0.3s ease;
            }
            
            .pets-toggle:hover {
                background: #96B48A;
                transform: translateY(-1px);
            }
            
            .pets-count {
                background: rgba(255, 255, 255, 0.2);
                padding: 2px 8px;
                border-radius: 10px;
                margin-left: 8px;
            }
            
            .pets-list {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 15px;
            }
            
            .pet-card {
                background: #f8f9fa;
                border-radius: 10px;
                padding: 15px;
                display: flex;
                align-items: center;
                gap: 12px;
                border: 1px solid #e0e0e0;
                transition: all 0.3s ease;
            }
            
            .pet-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            }
            
            .pet-icon {
                font-size: 2rem;
                width: 50px;
                height: 50px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--accent-warm-sand);
                border-radius: 50%;
            }
            
            .pet-info {
                flex: 1;
            }
            
            .pet-name {
                font-weight: 600;
                color: var(--neutral-charcoal);
                font-size: 1.1rem;
                margin-bottom: 4px;
            }
            
            .pet-details {
                color: #666;
                font-size: 0.9rem;
            }
            
            .pet-select-btn {
                background: var(--primary-sage);
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 500;
                transition: all 0.3s ease;
            }
            
            .pet-select-btn:hover {
                background: #96B48A;
            }
            
            /* Pet Detail Modal */
            .pet-detail-modal {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                display: none;
                z-index: 3000;
                align-items: center;
                justify-content: center;
            }
            
            .pet-detail-modal.active {
                display: flex;
            }
            
            .pet-detail-content {
                background: white;
                border-radius: 15px;
                width: 90%;
                max-width: 600px;
                max-height: 80vh;
                overflow-y: auto;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
            }
            
            .pet-detail-header {
                background: var(--primary-sage);
                color: white;
                padding: 20px;
                border-radius: 15px 15px 0 0;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }
            
            .pet-detail-header h3 {
                margin: 0;
                font-size: 1.3rem;
            }
            
            .close-pet-detail {
                background: rgba(255, 255, 255, 0.2);
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                cursor: pointer;
            }
            
            .pet-detail-body {
                padding: 20px;
            }
            
            .pet-detail-card {
                display: flex;
                gap: 20px;
                margin-bottom: 20px;
                padding: 20px;
                background: #f8f9fa;
                border-radius: 10px;
            }
            
            .pet-detail-icon {
                font-size: 3rem;
                width: 80px;
                height: 80px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--accent-warm-sand);
                border-radius: 50%;
            }
            
            .pet-detail-info {
                flex: 1;
            }
            
            .pet-detail-row {
                display: flex;
                margin-bottom: 8px;
            }
            
            .pet-detail-label {
                font-weight: 600;
                width: 80px;
                color: var(--neutral-charcoal);
            }
            
            .pet-detail-value {
                color: #666;
            }
            
            .pet-services-suggestion h4 {
                color: var(--neutral-charcoal);
                margin-bottom: 15px;
            }
            
            .service-suggestions {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 10px;
            }
            
            .service-suggestion-btn {
                background: var(--accent-dusty-rose);
                color: white;
                border: none;
                padding: 12px 16px;
                border-radius: 8px;
                cursor: pointer;
                font-weight: 500;
                transition: all 0.3s ease;
                text-align: left;
            }
            
            .service-suggestion-btn:hover {
                background: #D4A5A5;
                transform: translateY(-1px);
            }
            
            .pet-detail-actions {
                padding: 20px;
                border-top: 1px solid #e0e0e0;
                text-align: center;
            }
            
            /* Mobile responsiveness for pets */
            @media (max-width: 768px) {
                .customer-pets-display {
                    margin: 10px;
                    padding: 15px;
                }
                
                .pets-list {
                    grid-template-columns: 1fr;
                }
                
                .pet-detail-card {
                    flex-direction: column;
                    text-align: center;
                }
                
                .service-suggestions {
                    grid-template-columns: 1fr;
                }
            }
        `;
        
        // Remove existing enhanced style if present
        const existingStyle = document.getElementById('ui-fixes-enhanced');
        if (existingStyle) {
            existingStyle.remove();
        }
        
        document.head.appendChild(style);
    }

    // ... (include all other existing methods from the original chat system)
}

// Initialize enhanced chat system
document.addEventListener('DOMContentLoaded', function() {
    window.chatSystem = new ChatSystem();
    console.log('Enhanced chat system with pet display initialized');
});
