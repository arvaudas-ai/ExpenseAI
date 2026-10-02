document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('login-form');
    const button = document.getElementById('login-btn');
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
        button.textContent = 'Logging in...';
        setMessage('');

        const formData = new FormData(form);
        const payload = {
            email: formData.get('email')?.toString().trim() || '',
            password: formData.get('password')?.toString() || '',
        };

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                const detail = typeof data.detail === 'string' ? data.detail : 'Login failed.';
                setMessage(detail, true);
                return;
            }

            localStorage.setItem('expenseai_token', data.access_token);
            setMessage('Login successful. Redirecting...', false);
            window.location.href = '/dashboard';
        } catch (error) {
            setMessage('Unable to log in. Please try again.', true);
        } finally {
            button.disabled = false;
            button.textContent = 'Login';
        }
    });
});
