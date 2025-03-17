// DOM Elements
const typewriterElement = document.getElementById('typewriter');
const musicNotesContainer = document.querySelector('.music-notes-container');
const hamburger = document.querySelector('.hamburger');
const navLinks = document.querySelector('.nav-links');

// Typewriter effect
function typeWriter(element, text, speed = 100) {
    let i = 0;
    element.textContent = '';
    
    function type() {
        if (i < text.length) {
            element.textContent += text.charAt(i);
            i++;
            setTimeout(type, speed);
        }
    }
    
    type();
}

// Initialize typewriter effect
document.addEventListener('DOMContentLoaded', () => {
    // Start typewriter after a short delay
    setTimeout(() => {
        typeWriter(typewriterElement, 'Melody Wall Capstone Project', 80);
    }, 500);
    
    // Create floating music notes
    createMusicNotes();
    
    // Mobile navigation
    hamburger.addEventListener('click', () => {
        hamburger.classList.toggle('active');
        navLinks.classList.toggle('active');
    });
    
    // Close mobile menu when a nav link is clicked
    document.querySelectorAll('.nav-links a').forEach(link => {
        link.addEventListener('click', () => {
            hamburger.classList.remove('active');
            navLinks.classList.remove('active');
        });
    });
});

// Create floating music notes animation
function createMusicNotes() {
    const musicNotes = ['♩', '♪', '♫', '♬', '🎵', '🎶', '♭', '♮', '♯'];
    const numNotes = 20;
    
    for (let i = 0; i < numNotes; i++) {
        const note = document.createElement('div');
        const randomNote = musicNotes[Math.floor(Math.random() * musicNotes.length)];
        
        note.className = 'music-note';
        note.textContent = randomNote;
        note.style.left = `${Math.random() * 100}%`;
        note.style.animationDuration = `${15 + Math.random() * 30}s`;
        note.style.animationDelay = `${Math.random() * 5}s`;
        note.style.opacity = 0.1 + Math.random() * 0.4;
        note.style.fontSize = `${1 + Math.random() * 2}rem`;
        note.style.filter = `hue-rotate(${Math.random() * 360}deg)`;
        
        musicNotesContainer.appendChild(note);
    }
}

// Smooth scrolling for navigation links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Navbar scroll effect
window.addEventListener('scroll', () => {
    const navbar = document.querySelector('.navbar');
    if (window.scrollY > 50) {
        navbar.style.padding = '1rem 2rem';
        navbar.style.boxShadow = '0 4px 20px rgba(0, 0, 0, 0.1)';
    } else {
        navbar.style.padding = '1.5rem 2rem';
        navbar.style.boxShadow = '0 4px 28px rgba(0, 0, 0, 0.15)';
    }
});

// Add parallax effect to hero section
window.addEventListener('mousemove', (e) => {
    const hero = document.querySelector('.hero');
    const mouseX = e.clientX / window.innerWidth;
    const mouseY = e.clientY / window.innerHeight;
    const moveX = (mouseX - 0.5) * 20;
    const moveY = (mouseY - 0.5) * 20;
    
    document.querySelectorAll('.music-note').forEach(note => {
        note.style.transform = `translate(${moveX * Math.random()}px, ${moveY * Math.random()}px)`;
    });
}); 