document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('access_token') || localStorage.getItem('expenseai_token');
    const form = document.getElementById('assistant-form');
    const input = document.getElementById('assistant-message');
    const sendButton = document.getElementById('assistant-send-btn');
    const messages = document.getElementById('chat-messages');
    const errorBox = document.getElementById('assistant-error');
    const logoutButton = document.getElementById('logout-btn');

    if (!token) {
        window.location.href = '/login';
        return;
    }

    const escapeHtml = (text) => {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    const setError = (text = '', isWarning = false) => {
        errorBox.textContent = text;
        errorBox.hidden = !text;
        errorBox.classList.toggle('warning', Boolean(text) && isWarning);
        errorBox.classList.toggle('error', Boolean(text) && !isWarning);
    };

    const addMessage = (role, text) => {
        const message = document.createElement('div');
        message.className = `chat-message ${role}-message`;
        const label = role === 'user' ? 'You' : 'ExpenseAI assistant';
        message.innerHTML = `<span class="chat-label">${label}</span><p>${escapeHtml(text)}</p>`;
        messages.appendChild(message);
        messages.scrollTop = messages.scrollHeight;
    };

    document.querySelectorAll('.suggestion-button').forEach((button) => {
        button.addEventListener('click', () => {
            input.value = button.textContent;
            input.focus();
        });
    });

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const message = input.value.trim();
        if (!message) {
            setError('Enter a question before sending.');
            input.focus();
            return;
        }

        setError('');
        addMessage('user', message);
        input.value = '';
        sendButton.disabled = true;
        sendButton.textContent = 'Thinking...';

        try {
            const response = await fetch('/api/assistant/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ message }),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                const error = new Error(typeof data.detail === 'string' ? data.detail : 'The assistant could not answer right now.');
                error.rateLimited = response.status === 429;
                throw error;
            }
            addMessage('assistant', data.answer);
        } catch (error) {
            setError(error.message || 'The assistant could not answer right now.', Boolean(error?.rateLimited));
        } finally {
            sendButton.disabled = false;
            sendButton.textContent = 'Send question';
            input.focus();
        }
    });

    logoutButton.addEventListener('click', () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('expenseai_token');
        window.location.href = '/login';
    });
});
