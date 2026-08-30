const yearTarget = document.getElementById('year');
if (yearTarget) {
  yearTarget.textContent = new Date().getFullYear();
}

const form = document.getElementById('lead-form');
const successMessage = document.getElementById('form-success');

if (form) {
  form.addEventListener('submit', (event) => {
    event.preventDefault();

    const name = form.querySelector('input[name="name"]')?.value.trim() || 'friend';
    const email = form.querySelector('input[name="email"]')?.value.trim() || '';

    if (!email) {
      successMessage.textContent = 'Please add your email so we can contact you.';
      successMessage.style.color = '#fbbf24';
      return;
    }

    successMessage.textContent = `Thanks, ${name}! We’ll be in touch shortly.`;
    successMessage.style.color = '#34d399';
    form.reset();
  });
}
