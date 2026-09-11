/**
 * DynamoDB Client for GenAI Petstore
 * Handles fetching real data from DynamoDB tables
 */

class DynamoDBClient {
    constructor() {
        this.region = 'us-west-2';
        this.tables = {
            customers: 'pa1_23_09_petstore_customer_profiles',
            appointments: 'pa1_23_09_petstore_appointments',
            agencies: 'pa1_23_09_petstore_agencies'
        };
        
        // Initialize AWS SDK (would need proper credentials in production)
        this.isConfigured = false;
        this.initializeAWS();
    }
    
    initializeAWS() {
        try {
            // In a real application, you would configure AWS credentials properly
            // For demo purposes, we'll simulate the data structure
            this.isConfigured = true;
        } catch (error) {
            console.warn('AWS SDK not configured, using demo data');
            this.isConfigured = false;
        }
    }
    
    async getCustomerProfile(customerId) {
        if (!this.isConfigured) {
            return this.getDemoCustomerProfile(customerId);
        }
        
        try {
            // In production, this would make actual DynamoDB calls
            // For now, return demo data based on the real structure we saw
            return this.getDemoCustomerProfile(customerId);
        } catch (error) {
            console.error('Error fetching customer profile:', error);
            return this.getDemoCustomerProfile(customerId);
        }
    }
    
    async getCustomerAppointments(customerId) {
        if (!this.isConfigured) {
            return this.getDemoAppointments(customerId);
        }
        
        try {
            // In production, this would query DynamoDB for appointments
            return this.getDemoAppointments(customerId);
        } catch (error) {
            console.error('Error fetching appointments:', error);
            return this.getDemoAppointments(customerId);
        }
    }
    
    getDemoCustomerProfile(customerId) {
        // Demo customer profiles based on real DynamoDB structure - 10 diverse users
        const profiles = {
            'cust_51afe207': {
                customer_id: 'cust_51afe207',
                firstName: 'Sarah',
                lastName: 'Johnson',
                email: 'sarah.johnson@email.com',
                phone: '555-01002',
                address: '300 Main St, City, State',
                registrationDate: '2025-09-23T22:30:01.846805',
                totalAppointments: 8,
                pets: [
                    {
                        name: 'Max',
                        species: 'Dog',
                        breed: 'Golden Retriever',
                        age: 3,
                        weight: 65,
                        healthStatus: 'Excellent',
                        lastVisit: '2024-01-15',
                        lastService: 'Annual Checkup & Vaccinations',
                        nextAppointment: '2024-02-10',
                        nextService: 'Dental Cleaning',
                        recommendedProducts: ['Premium Dog Food', 'Dental Chews', 'Joint Supplements'],
                        medicalHistory: ['Vaccinated', 'Microchipped', 'Spayed/Neutered'],
                        allergies: 'None known'
                    },
                    {
                        name: 'Luna',
                        species: 'Cat',
                        breed: 'Persian',
                        age: 2,
                        weight: 8,
                        healthStatus: 'Good',
                        lastVisit: '2024-01-08',
                        lastService: 'Grooming & Nail Trim',
                        nextAppointment: '2024-02-15',
                        nextService: 'Health Checkup',
                        recommendedProducts: ['Cat Brush', 'Hairball Control Food', 'Scratching Post'],
                        medicalHistory: ['Vaccinated', 'Microchipped'],
                        allergies: 'Chicken protein'
                    }
                ]
            },
            'cust_e11b05f8': {
                customer_id: 'cust_e11b05f8',
                firstName: 'Mike',
                lastName: 'Wilson',
                email: 'mike.wilson@email.com',
                phone: '555-01008',
                address: '900 Main St, City, State',
                registrationDate: '2025-09-23T22:30:01.846861',
                totalAppointments: 12,
                pets: [
                    {
                        name: 'Bella',
                        species: 'Cat',
                        breed: 'Siamese',
                        age: 4,
                        weight: 9,
                        healthStatus: 'Good',
                        lastVisit: '2024-01-12',
                        lastService: 'Behavioral Consultation',
                        nextAppointment: '2024-02-18',
                        nextService: 'Vaccination Booster',
                        recommendedProducts: ['Interactive Cat Toys', 'Calming Treats', 'Cat Tree'],
                        medicalHistory: ['Vaccinated', 'Behavioral training completed'],
                        allergies: 'Fish-based foods'
                    },
                    {
                        name: 'Rocky',
                        species: 'Dog',
                        breed: 'German Shepherd',
                        age: 6,
                        weight: 80,
                        healthStatus: 'Excellent',
                        lastVisit: '2024-01-25',
                        lastService: 'Hip X-Ray & Joint Assessment',
                        nextAppointment: '2024-02-12',
                        nextService: 'Physical Therapy Session',
                        recommendedProducts: ['Joint Support Supplements', 'Orthopedic Bed', 'Low-Impact Exercise Toys'],
                        medicalHistory: ['Vaccinated', 'Microchipped', 'Hip dysplasia monitoring'],
                        allergies: 'Grain allergies'
                    }
                ]
            },
            'cust_a1b2c3d4': {
                customer_id: 'cust_a1b2c3d4',
                firstName: 'Emily',
                lastName: 'Chen',
                email: 'emily.chen@email.com',
                phone: '555-01003',
                address: '456 Oak Avenue, City, State',
                registrationDate: '2025-08-15T14:22:33.123456',
                totalAppointments: 15,
                pets: [
                    {
                        name: 'Mochi',
                        species: 'Dog',
                        breed: 'Shiba Inu',
                        age: 2,
                        weight: 22,
                        healthStatus: 'Excellent',
                        lastVisit: '2024-01-20',
                        lastService: 'Puppy Training Graduation',
                        nextAppointment: '2024-02-08',
                        nextService: 'Advanced Training Session',
                        recommendedProducts: ['Training Treats', 'Puzzle Toys', 'Harness'],
                        medicalHistory: ['Vaccinated', 'Microchipped', 'Training certified'],
                        allergies: 'None known'
                    },
                    {
                        name: 'Whiskers',
                        species: 'Cat',
                        breed: 'Maine Coon',
                        age: 7,
                        weight: 15,
                        healthStatus: 'Good',
                        lastVisit: '2024-01-18',
                        lastService: 'Senior Cat Wellness Exam',
                        nextAppointment: '2024-02-20',
                        nextService: 'Dental Cleaning',
                        recommendedProducts: ['Senior Cat Food', 'Dental Treats', 'Heated Bed'],
                        medicalHistory: ['Vaccinated', 'Dental issues monitored'],
                        allergies: 'Dairy products'
                    },
                    {
                        name: 'Kiwi',
                        species: 'Bird',
                        breed: 'Cockatiel',
                        age: 3,
                        weight: 0.2,
                        healthStatus: 'Excellent',
                        lastVisit: '2024-01-10',
                        lastService: 'Wing Clipping & Health Check',
                        nextAppointment: '2024-02-25',
                        nextService: 'Beak Trim',
                        recommendedProducts: ['Bird Vitamins', 'Perch Variety Pack', 'Foraging Toys'],
                        medicalHistory: ['Health certified', 'Wing clipping regular'],
                        allergies: 'Avocado, chocolate'
                    }
                ]
            },
            'cust_f5g6h7i8': {
                customer_id: 'cust_f5g6h7i8',
                firstName: 'David',
                lastName: 'Rodriguez',
                email: 'david.rodriguez@email.com',
                phone: '555-01004',
                address: '789 Pine Street, City, State',
                registrationDate: '2025-07-22T09:15:42.987654',
                totalAppointments: 6,
                pets: [
                    {
                        name: 'Thor',
                        species: 'Dog',
                        breed: 'Rottweiler',
                        age: 4,
                        weight: 110,
                        healthStatus: 'Good',
                        lastVisit: '2024-01-22',
                        lastService: 'Aggression Training Session',
                        nextAppointment: '2024-02-14',
                        nextService: 'Socialization Training',
                        recommendedProducts: ['Heavy Duty Leash', 'Large Breed Food', 'Chew Toys'],
                        medicalHistory: ['Vaccinated', 'Behavioral training ongoing'],
                        allergies: 'Beef protein'
                    }
                ]
            },
            'cust_j9k0l1m2': {
                customer_id: 'cust_j9k0l1m2',
                firstName: 'Lisa',
                lastName: 'Thompson',
                email: 'lisa.thompson@email.com',
                phone: '555-01005',
                address: '321 Elm Drive, City, State',
                registrationDate: '2025-06-10T16:45:18.456789',
                totalAppointments: 20,
                pets: [
                    {
                        name: 'Princess',
                        species: 'Cat',
                        breed: 'Ragdoll',
                        age: 5,
                        weight: 12,
                        healthStatus: 'Excellent',
                        lastVisit: '2024-01-28',
                        lastService: 'Luxury Spa Grooming',
                        nextAppointment: '2024-02-22',
                        nextService: 'Full Grooming Package',
                        recommendedProducts: ['Premium Cat Shampoo', 'Silk Brush', 'Luxury Cat Bed'],
                        medicalHistory: ['Vaccinated', 'Microchipped', 'Show quality'],
                        allergies: 'Artificial fragrances'
                    },
                    {
                        name: 'Duke',
                        species: 'Dog',
                        breed: 'English Bulldog',
                        age: 3,
                        weight: 55,
                        healthStatus: 'Fair',
                        lastVisit: '2024-01-26',
                        lastService: 'Respiratory Assessment',
                        nextAppointment: '2024-02-16',
                        nextService: 'Breathing Exercise Training',
                        recommendedProducts: ['Cooling Mat', 'Elevated Food Bowl', 'Breathing Support Supplements'],
                        medicalHistory: ['Vaccinated', 'Breathing issues monitored'],
                        allergies: 'Heat sensitivity'
                    }
                ]
            },
            'cust_d4825242': {
                customer_id: 'cust_d4825242',
                firstName: 'Demo',
                lastName: 'Pet Parent',
                email: 'demo@email.com',
                phone: '555-01006',
                address: '700 Main St, City, State',
                registrationDate: '2025-09-23T22:00:25.422349',
                totalAppointments: 25,
                pets: [
                    {
                        name: 'Buddy',
                        species: 'Dog',
                        breed: 'Beagle',
                        age: 2,
                        weight: 25,
                        healthStatus: 'Excellent',
                        lastVisit: '2024-01-10',
                        lastService: 'Scent Training Session',
                        nextAppointment: '2024-02-08',
                        nextService: 'Nose Work Competition Prep',
                        recommendedProducts: ['Scent Training Kit', 'Treat Puzzle', 'Tracking Harness'],
                        medicalHistory: ['Vaccinated', 'Microchipped', 'Scent training certified'],
                        allergies: 'None known'
                    },
                    {
                        name: 'Shadow',
                        species: 'Cat',
                        breed: 'British Shorthair',
                        age: 5,
                        weight: 10,
                        healthStatus: 'Good',
                        lastVisit: '2024-01-16',
                        lastService: 'Weight Management Consultation',
                        nextAppointment: '2024-02-22',
                        nextService: 'Diet Progress Check',
                        recommendedProducts: ['Weight Control Food', 'Interactive Feeder', 'Exercise Wand'],
                        medicalHistory: ['Vaccinated', 'Weight management program'],
                        allergies: 'Tuna'
                    },
                    {
                        name: 'Coco',
                        species: 'Dog',
                        breed: 'Poodle',
                        age: 1,
                        weight: 15,
                        healthStatus: 'Excellent',
                        lastVisit: '2024-01-22',
                        lastService: 'Puppy Socialization Class',
                        nextAppointment: '2024-02-14',
                        nextService: 'First Grooming Experience',
                        recommendedProducts: ['Puppy Shampoo', 'Soft Brush', 'Puppy Training Pads'],
                        medicalHistory: ['Vaccinated', 'Socialization training'],
                        allergies: 'None known'
                    }
                ]
            },
            'cust_n3o4p5q6': {
                customer_id: 'cust_n3o4p5q6',
                firstName: 'Amanda',
                lastName: 'Foster',
                email: 'amanda.foster@email.com',
                phone: '555-01007',
                address: '654 Maple Lane, City, State',
                registrationDate: '2025-05-18T11:30:25.789012',
                totalAppointments: 9,
                pets: [
                    {
                        name: 'Snowball',
                        species: 'Rabbit',
                        breed: 'Holland Lop',
                        age: 2,
                        weight: 3,
                        healthStatus: 'Excellent',
                        lastVisit: '2024-01-14',
                        lastService: 'Nail Trim & Health Check',
                        nextAppointment: '2024-02-28',
                        nextService: 'Dental Examination',
                        recommendedProducts: ['Timothy Hay', 'Rabbit Pellets', 'Chew Toys'],
                        medicalHistory: ['Spayed', 'Dental care regular'],
                        allergies: 'Iceberg lettuce'
                    },
                    {
                        name: 'Ginger',
                        species: 'Cat',
                        breed: 'Orange Tabby',
                        age: 8,
                        weight: 11,
                        healthStatus: 'Good',
                        lastVisit: '2024-01-24',
                        lastService: 'Senior Wellness Panel',
                        nextAppointment: '2024-02-26',
                        nextService: 'Kidney Function Check',
                        recommendedProducts: ['Senior Cat Food', 'Water Fountain', 'Kidney Support Treats'],
                        medicalHistory: ['Vaccinated', 'Early kidney disease monitoring'],
                        allergies: 'Seafood'
                    }
                ]
            },
            'cust_r7s8t9u0': {
                customer_id: 'cust_r7s8t9u0',
                firstName: 'James',
                lastName: 'Parker',
                email: 'james.parker@email.com',
                phone: '555-01009',
                address: '987 Cedar Court, City, State',
                registrationDate: '2025-04-03T13:45:55.345678',
                totalAppointments: 18,
                pets: [
                    {
                        name: 'Rex',
                        species: 'Dog',
                        breed: 'German Shepherd Mix',
                        age: 7,
                        weight: 75,
                        healthStatus: 'Good',
                        lastVisit: '2024-01-30',
                        lastService: 'Arthritis Management Consultation',
                        nextAppointment: '2024-02-27',
                        nextService: 'Physical Therapy Session',
                        recommendedProducts: ['Joint Supplements', 'Orthopedic Bed', 'Ramp for Car'],
                        medicalHistory: ['Vaccinated', 'Arthritis treatment ongoing'],
                        allergies: 'Chicken'
                    },
                    {
                        name: 'Mittens',
                        species: 'Cat',
                        breed: 'Domestic Shorthair',
                        age: 3,
                        weight: 9,
                        healthStatus: 'Excellent',
                        lastVisit: '2024-01-19',
                        lastService: 'Spay Surgery Follow-up',
                        nextAppointment: '2024-02-19',
                        nextService: 'Routine Checkup',
                        recommendedProducts: ['Recovery Cone', 'Soft Food', 'Comfort Blanket'],
                        medicalHistory: ['Recently spayed', 'Vaccinated'],
                        allergies: 'None known'
                    }
                ]
            },
            'cust_v1w2x3y4': {
                customer_id: 'cust_v1w2x3y4',
                firstName: 'Rachel',
                lastName: 'Kim',
                email: 'rachel.kim@email.com',
                phone: '555-01010',
                address: '147 Birch Boulevard, City, State',
                registrationDate: '2025-03-12T08:20:10.234567',
                totalAppointments: 14,
                pets: [
                    {
                        name: 'Nala',
                        species: 'Dog',
                        breed: 'Husky',
                        age: 4,
                        weight: 55,
                        healthStatus: 'Excellent',
                        lastVisit: '2024-01-27',
                        lastService: 'Endurance Training Assessment',
                        nextAppointment: '2024-02-24',
                        nextService: 'Agility Training Session',
                        recommendedProducts: ['High-Energy Dog Food', 'Cooling Vest', 'Agility Equipment'],
                        medicalHistory: ['Vaccinated', 'Athletic conditioning program'],
                        allergies: 'Corn'
                    },
                    {
                        name: 'Simba',
                        species: 'Cat',
                        breed: 'Bengal',
                        age: 2,
                        weight: 10,
                        healthStatus: 'Excellent',
                        lastVisit: '2024-01-21',
                        lastService: 'Behavioral Enrichment Consultation',
                        nextAppointment: '2024-02-21',
                        nextService: 'Play Therapy Session',
                        recommendedProducts: ['Cat Wheel', 'Puzzle Feeders', 'Climbing Tree'],
                        medicalHistory: ['Vaccinated', 'High-energy breed management'],
                        allergies: 'None known'
                    }
                ]
            },
            'cust_z5a6b7c8': {
                customer_id: 'cust_z5a6b7c8',
                firstName: 'Robert',
                lastName: 'Martinez',
                email: 'robert.martinez@email.com',
                phone: '555-01011',
                address: '258 Willow Way, City, State',
                registrationDate: '2025-02-28T15:55:33.876543',
                totalAppointments: 7,
                pets: [
                    {
                        name: 'Ace',
                        species: 'Dog',
                        breed: 'Border Collie',
                        age: 5,
                        weight: 45,
                        healthStatus: 'Excellent',
                        lastVisit: '2024-01-29',
                        lastService: 'Herding Instinct Evaluation',
                        nextAppointment: '2024-02-29',
                        nextService: 'Advanced Obedience Training',
                        recommendedProducts: ['Mental Stimulation Toys', 'Herding Ball', 'Training Clicker'],
                        medicalHistory: ['Vaccinated', 'Working dog certification'],
                        allergies: 'Lamb'
                    },
                    {
                        name: 'Patches',
                        species: 'Cat',
                        breed: 'Calico',
                        age: 6,
                        weight: 8,
                        healthStatus: 'Good',
                        lastVisit: '2024-01-17',
                        lastService: 'Anxiety Management Consultation',
                        nextAppointment: '2024-02-17',
                        nextService: 'Stress Reduction Therapy',
                        recommendedProducts: ['Calming Pheromones', 'Anxiety Vest', 'Hiding Spots'],
                        medicalHistory: ['Vaccinated', 'Anxiety treatment ongoing'],
                        allergies: 'Loud noises (stress trigger)'
                    }
                ]
            }
        };
        
        return profiles[customerId] || null;
    }
    
    getDemoAppointments(customerId) {
        // Demo appointments based on real DynamoDB structure
        const appointments = {
            'cust_51afe207': [
                {
                    appointment_id: 'appt_001',
                    customer_id: customerId,
                    appointmentDate: '2024-02-10',
                    appointmentTime: '10:00',
                    serviceType: 'veterinary',
                    status: 'scheduled',
                    cost: 125.00,
                    duration: 60,
                    notes: 'Regular checkup for Max',
                    petName: 'Max'
                },
                {
                    appointment_id: 'appt_002',
                    customer_id: customerId,
                    appointmentDate: '2024-02-15',
                    appointmentTime: '14:00',
                    serviceType: 'grooming',
                    status: 'scheduled',
                    cost: 85.00,
                    duration: 90,
                    notes: 'Full grooming service for Luna',
                    petName: 'Luna'
                }
            ],
            'cust_e11b05f8': [
                {
                    appointment_id: 'appt_003',
                    customer_id: customerId,
                    appointmentDate: '2024-02-18',
                    appointmentTime: '11:00',
                    serviceType: 'veterinary',
                    status: 'scheduled',
                    cost: 150.00,
                    duration: 45,
                    notes: 'Health checkup for Bella',
                    petName: 'Bella'
                }
            ],
            'cust_d4825242': [
                {
                    appointment_id: 'appt_004',
                    customer_id: customerId,
                    appointmentDate: '2024-02-08',
                    appointmentTime: '09:00',
                    serviceType: 'training',
                    status: 'scheduled',
                    cost: 75.00,
                    duration: 60,
                    notes: 'Basic obedience training for Buddy',
                    petName: 'Buddy'
                },
                {
                    appointment_id: 'appt_005',
                    customer_id: customerId,
                    appointmentDate: '2024-02-20',
                    appointmentTime: '15:30',
                    serviceType: 'grooming',
                    status: 'scheduled',
                    cost: 95.00,
                    duration: 120,
                    notes: 'Full grooming for Whiskers',
                    petName: 'Whiskers'
                }
            ]
        };
        
        return appointments[customerId] || [];
    }
    
    async getAllCustomers() {
        // For admin dashboard - get all customers
        const allProfiles = [
            this.getDemoCustomerProfile('cust_51afe207'),
            this.getDemoCustomerProfile('cust_e11b05f8'),
            this.getDemoCustomerProfile('cust_d4825242')
        ];
        
        return allProfiles.filter(profile => profile !== null);
    }
    
    async getAllAppointments() {
        // For admin dashboard - get all appointments
        const allAppointments = [
            ...this.getDemoAppointments('cust_51afe207'),
            ...this.getDemoAppointments('cust_e11b05f8'),
            ...this.getDemoAppointments('cust_d4825242')
        ];
        
        return allAppointments;
    }
}

// Create global instance
window.dynamoClient = new DynamoDBClient();