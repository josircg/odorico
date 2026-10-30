document.addEventListener('DOMContentLoaded', () => {
  const submitButtons = document.querySelectorAll('form button[type="submit"], form input[type="submit"]');

  submitButtons.forEach(button => {
    button.addEventListener('click', function(e) {
      const form = this.form;
      if (form && !form.checkValidity()) return;

      if (this.classList.contains('submitting')) {
        e.preventDefault();
        return;
      }

      const clickedButton = this;

      form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(btn => {
        btn.classList.add('submitting');
        if (btn !== clickedButton) btn.disabled = true;
      });

      if (clickedButton.tagName === 'BUTTON') {
        clickedButton.insertAdjacentHTML('afterbegin',
          '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>'
        );
      }
    });
  });
});