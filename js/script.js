document.addEventListener('DOMContentLoaded', () => {
    const text = "Melody Wall Capstone Project";
    const typewriter = document.getElementById('typewriter');
    let i = 0;

    function typeEffect() {
        if (i < text.length) {
            typewriter.textContent += text.charAt(i);
            i++;
            setTimeout(type, 100);
        }
    }

    type();
});
