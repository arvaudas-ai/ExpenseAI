document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('register-form');
    const button = document.getElementById('register-btn');
    const messageBox = document.getElementById('form-message');

    if (!form || !button || !messageBox) return;

    const setMessage = (text, isError = false) => {
        messageBox.textContent = text;
        messageBox.classList.toggle('error', isError);
        messageBox.classList.toggle('success', !isError);
    };

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        button.disabled = true;
        button.textContent = 'Creating account...';
        setMessage('');

        const formData = new FormData(form);
        const payload = {
            name: formData.get('name')?.toString().trim() || '',
            email: formData.get('email')?.toString().trim() || '',
            password: formData.get('password')?.toString() || '',
            password_confirmation: formData.get('password_confirmation')?.toString() || '',
        };

        try {
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                const detail = typeof data.detail === 'string' ? data.detail : 'Registration failed.';
                setMessage(detail, true);
                return;
            }

            setMessage('Registration successful! Your account has been created.', false);
            form.reset();
        } catch (error) {
            setMessage('Unable to create account. Please try again.', true);
        } finally {
            button.disabled = false;
            button.textContent = 'Create Account';
        }
    });
});
