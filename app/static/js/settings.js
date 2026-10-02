document.addEventListener('DOMContentLoaded', async () => {
    const profileForm = document.getElementById('profile-form');
    const passwordForm = document.getElementById('password-form');
    const saveButton = document.getElementById('save-profile-btn');
    const passwordButton = document.getElementById('change-password-btn');
    const logoutButton = document.getElementById('logout-btn');
    const messageBox = document.getElementById('form-message');

    const token = localStorage.getItem('expenseai_token') || localStorage.getItem('access_token');
    if (!token) {
        window.location.href = '/login';
        return;
    }

    const setMessage = (text = '', isError = false) => {
        messageBox.textContent = text;
        messageBox.classList.toggle('error', Boolean(text) && isError);
        messageBox.classList.toggle('success', Boolean(text) && !isError);
        if (!text) {
            messageBox.classList.remove('error', 'success');
        }
    };

    const setLoading = (button, isLoading, defaultText) => {
        button.disabled = isLoading;
        button.textContent = isLoading ? 'Loading...' : defaultText;
    };

    const loadProfile = async () => {
        setLoading(saveButton, true, 'Save Changes');
        setLoading(passwordButton, true, 'Update Password');

        try {
            const response = await fetch('/api/users/me', {
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            });

            if (!response.ok) {
                throw new Error('Unable to load profile.');
            }

            const user = await response.json();
            document.getElementById('name').value = user.name || '';
            document.getElementById('email').value = user.email || '';
            document.getElementById('currency').value = user.currency || 'USD';

            const preferences = user.preferences || {};
            document.getElementById('theme').value = preferences.theme || 'system';
            document.getElementById('budget-alerts').checked = Boolean(preferences.budget_alerts);
        } catch (error) {
            setMessage(error.message || 'Unable to load profile.', true);
        } finally {
            setLoading(saveButton, false, 'Save Changes');
            setLoading(passwordButton, false, 'Update Password');
        }
    };

    profileForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        setLoading(saveButton, true, 'Save Changes');
        setMessage('');

        const payload = {
            name: document.getElementById('name').value.trim(),
            email: document.getElementById('email').value.trim(),
            currency: document.getElementById('currency').value,
            preferences: {
                theme: document.getElementById('theme').value,
                budget_alerts: document.getElementById('budget-alerts').checked,
            },
        };

        try {
            const response = await fetch('/api/users/me', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify(payload),
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                const detail = typeof data.detail === 'string' ? data.detail : 'Unable to save profile.';
                throw new Error(detail);
            }

            setMessage('Profile updated successfully.', false);
        } catch (error) {
            setMessage(error.message || 'Profile update failed.', true);
        } finally {
            setLoading(saveButton, false, 'Save Changes');
        }
    });

    passwordForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        setLoading(passwordButton, true, 'Update Password');
        setMessage('');

        const currentPassword = document.getElementById('current-password').value;
        const newPassword = document.getElementById('new-password').value;
        const confirmPassword = document.getElementById('confirm-password').value;

        if (!currentPassword || !newPassword || !confirmPassword) {
            setMessage('Please complete all password fields.', true);
            setLoading(passwordButton, false, 'Update Password');
            return;
        }

        const payload = {
            current_password: currentPassword,
            new_password: newPassword,
            confirm_new_password: confirmPassword,
        };

        try {
            const response = await fetch('/api/users/me/password', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify(payload),
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                const detail = typeof data.detail === 'string' ? data.detail : 'Password update failed.';
                throw new Error(detail);
            }

            passwordForm.reset();
            setMessage('Password updated successfully.', false);
        } catch (error) {
            setMessage(error.message || 'Password update failed.', true);
        } finally {
            setLoading(passwordButton, false, 'Update Password');
        }
    });

    logoutButton.addEventListener('click', () => {
        localStorage.removeItem('expenseai_token');
        localStorage.removeItem('access_token');
        window.location.href = '/login';
    });

    loadProfile();
});
