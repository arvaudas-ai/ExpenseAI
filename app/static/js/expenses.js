document.addEventListener('DOMContentLoaded', async () => {
    const expenseForm = document.getElementById('expense-form');
    const submitButton = document.getElementById('submit-expense-btn');
    const logoutButton = document.getElementById('logout-btn');
    const formMessage = document.getElementById('form-message');
    const expensesBody = document.getElementById('expenses-body');
    const expensesTable = document.getElementById('expenses-table');
    const expensesEmpty = document.getElementById('expenses-empty');
    const categorySelect = document.getElementById('category-id');
    const expenseFilters = document.getElementById('expense-filters');
    const expenseListMessage = document.getElementById('expense-list-message');
    const previousPageButton = document.getElementById('expenses-prev-page');
    const nextPageButton = document.getElementById('expenses-next-page');
    const pageLabel = document.getElementById('expenses-page-label');
    const pageSizeSelect = document.getElementById('expenses-page-size');
    const editModal = document.getElementById('edit-expense-modal');
    const closeModalBtn = document.getElementById('close-expense-modal');
    const editForm = document.getElementById('edit-expense-form');
    const editCategorySelect = document.getElementById('edit-category-id');

    const token = localStorage.getItem('access_token') || localStorage.getItem('expenseai_token');
    if (!token) {
        window.location.href = '/login';
        return;
    }

    let categories = [];
    let currentOffset = 0;
    let currentLimit = Number(pageSizeSelect.value);
    let listRequestId = 0;

    const setMessage = (text = '', isError = false) => {
        formMessage.textContent = text;
        formMessage.classList.toggle('error', Boolean(text) && isError);
        formMessage.classList.toggle('success', Boolean(text) && !isError);
        if (!text) {
            formMessage.classList.remove('error', 'success');
        }
    };

    const setButtonState = (button, loading, label) => {
        button.disabled = loading;
        button.textContent = loading ? 'Loading...' : label;
    };

    let currentCurrency = 'USD';
    let currencyFormat = new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: currentCurrency,
    });

    // Icon mapping for emoji display
    const iconMap = {
        'food': '🍔', 'transport': '🚗', 'utilities': '💡', 'entertainment': '🎬',
        'shopping': '🛍️', 'health': '⚕️', 'education': '📚', 'travel': '✈️',
        'dining': '🍽️', 'groceries': '🛒', 'gas': '⛽', 'electricity': '⚡',
        'water': '💧', 'internet': '📶', 'phone': '📱', 'movie': '🎥',
        'music': '🎵', 'books': '📖', 'sports': '⚽', 'gym': '🏋️',
        'medical': '🏥', 'pharmacy': '💊', 'doctor': '👨‍⚕️', 'school': '🎓',
        'tuition': '🎓', 'plane': '✈️', 'hotel': '🏨', 'taxi': '🚕', 'other': '📌'
    };

    const loadCategories = async () => {
        try {
            const response = await fetch('/api/categories', {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (!response.ok) {
                throw new Error('Failed to load categories');
            }

            categories = await response.json();

            // Populate category selects
            categorySelect.innerHTML = '<option value="">-- Select a category --</option>';
            editCategorySelect.innerHTML = '<option value="">-- Select a category --</option>';

            const filterCategorySelect = document.getElementById('expense-filter-category');
            filterCategorySelect.innerHTML = '<option value="">All categories</option>';

            categories.forEach(cat => {
                const option = document.createElement('option');
                option.value = cat.id;
                option.textContent = `${iconMap[cat.icon] || '📌'} ${cat.name}`;
                categorySelect.appendChild(option);

                const editOption = document.createElement('option');
                editOption.value = cat.id;
                editOption.textContent = `${iconMap[cat.icon] || '📌'} ${cat.name}`;
                editCategorySelect.appendChild(editOption);

                const filterOption = document.createElement('option');
                filterOption.value = cat.id;
                filterOption.textContent = cat.name;
                filterCategorySelect.appendChild(filterOption);
            });
        } catch (error) {
            setMessage('Failed to load categories: ' + error.message, true);
        }
    };

    const renderExpenses = (expenses) => {
        expensesBody.innerHTML = '';

        if (!expenses.length) {
            expensesTable.style.display = 'none';
            expensesEmpty.style.display = 'block';
            const hasFilters = [
                'expense-search', 'expense-start-date', 'expense-end-date',
                'expense-filter-category', 'expense-filter-payment',
                'expense-amount-min', 'expense-amount-max',
            ].some((id) => Boolean(document.getElementById(id).value));
            expensesEmpty.classList.toggle('warning-state', hasFilters);
            expensesEmpty.textContent = hasFilters
                ? 'No expenses match these search and filter settings.'
                : 'No expenses yet. Add your first expense above.';
            return;
        }

        expensesTable.style.display = 'table';
        expensesEmpty.style.display = 'none';
        expensesEmpty.classList.remove('warning-state');

        for (const expense of expenses) {
            const category = expense.category || {};
            const categoryName = category.name || 'Uncategorized';
            const categoryIcon = iconMap[category.icon] || '📌';
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td style="padding:8px;">${currencyFormat.format(Number(expense.amount))}</td>
                <td style="padding:8px; color: ${category.color || '#000'};">
                    ${categoryIcon} ${escapeHtml(categoryName)}
                </td>
                <td style="padding:8px;">${escapeHtml(expense.description)}</td>
                <td style="padding:8px;">${expense.date}</td>
                <td style="padding:8px;">${expense.payment_method}</td>
                <td style="padding:8px;">
                    <button type="button" data-action="edit" data-id="${expense.id}" class="secondary">Edit</button>
                    <button type="button" data-action="delete" data-id="${expense.id}" class="danger">Delete</button>
                </td>
            `;
            expensesBody.appendChild(row);
        }

        expensesBody.querySelectorAll('button[data-action="delete"]').forEach((button) => {
            button.addEventListener('click', async () => {
                const id = Number(button.dataset.id);
                await deleteExpense(id);
            });
        });

        expensesBody.querySelectorAll('button[data-action="edit"]').forEach((button) => {
            button.addEventListener('click', async () => {
                const id = Number(button.dataset.id);
                await openEditModal(id);
            });
        });
    };

    const buildExpenseQuery = () => {
        const params = new URLSearchParams();
        const search = document.getElementById('expense-search').value.trim();
        const startDate = document.getElementById('expense-start-date').value;
        const endDate = document.getElementById('expense-end-date').value;
        const categoryId = document.getElementById('expense-filter-category').value;
        const paymentMethod = document.getElementById('expense-filter-payment').value;
        const amountMin = document.getElementById('expense-amount-min').value;
        const amountMax = document.getElementById('expense-amount-max').value;
        const [sortBy, sortOrder] = document.getElementById('expense-sort').value.split(':');
        if (search) params.set('search', search);
        if (startDate) params.set('start_date', startDate);
        if (endDate) params.set('end_date', endDate);
        if (categoryId) params.set('category_id', categoryId);
        if (paymentMethod) params.set('payment_method', paymentMethod);
        if (amountMin) params.set('amount_min', amountMin);
        if (amountMax) params.set('amount_max', amountMax);
        params.set('sort_by', sortBy);
        params.set('sort_order', sortOrder);
        params.set('limit', String(currentLimit));
        params.set('offset', String(currentOffset));
        return params;
    };

    const fetchExpenses = async () => {
        const requestId = ++listRequestId;
        setButtonState(submitButton, true, 'Add Expense');
        expenseListMessage.textContent = 'Loading expenses...';
        try {
            const response = await fetch(`/api/expenses?${buildExpenseQuery().toString()}`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            const data = await response.json().catch(() => []);
            if (requestId !== listRequestId) return;
            if (!response.ok) {
                throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to load expenses.');
            }
            renderExpenses(Array.isArray(data) ? data : []);
            const pageNumber = Math.floor(currentOffset / currentLimit) + 1;
            pageLabel.textContent = `Page ${pageNumber}`;
            previousPageButton.disabled = currentOffset === 0;
            nextPageButton.disabled = data.length < currentLimit;
            expenseListMessage.textContent = data.length ? `${data.length} expense${data.length === 1 ? '' : 's'} on this page.` : '';
        } catch (error) {
            if (requestId !== listRequestId) return;
            renderExpenses([]);
            expensesEmpty.textContent = 'Unable to load expenses.';
            expenseListMessage.textContent = error.message || 'Unable to load expenses.';
            expenseListMessage.classList.add('error');
        } finally {
            if (requestId === listRequestId) setButtonState(submitButton, false, 'Add Expense');
        }
    };

    const loadProfile = async () => {
        const response = await fetch('/api/auth/me', {
            headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to load your profile.');
        }
        currentCurrency = data.currency || 'USD';
        currencyFormat = new Intl.NumberFormat(undefined, {
            style: 'currency',
            currency: currentCurrency,
        });
        const currencyLabel = document.getElementById('expense-currency');
        if (currencyLabel) currencyLabel.textContent = currentCurrency;
    };

    const deleteExpense = async (id) => {
        if (!confirm('Are you sure you want to delete this expense?')) {
            return;
        }

        try {
            const response = await fetch(`/api/expenses/${id}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${token}`,
                },
            });

            if (!response.ok && response.status !== 204) {
                const data = await response.json().catch(() => ({}));
                throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to delete expense.');
            }

            setMessage('Expense deleted successfully.', false);
            await fetchExpenses();
        } catch (error) {
            setMessage(error.message || 'Unable to delete expense.', true);
        }
    };

    const openEditModal = async (id) => {
        try {
            const response = await fetch(`/api/expenses/${id}`, {
                headers: {
                    'Authorization': `Bearer ${token}`,
                },
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to fetch expense.');
            }

            document.getElementById('edit-expense-id').value = id;
            document.getElementById('edit-amount').value = Number(data.amount);
            document.getElementById('edit-category-id').value = data.category_id || '';
            document.getElementById('edit-description').value = data.description;
            document.getElementById('edit-date').value = data.date;
            document.getElementById('edit-payment-method').value = data.payment_method;
            editModal.hidden = false;
        } catch (error) {
            setMessage(error.message || 'Unable to edit expense.', true);
        }
    };

    expenseForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        setButtonState(submitButton, true, 'Add expense');
        setMessage('');

        const selectedCategoryId = Number(categorySelect.value);
        if (!selectedCategoryId) {
            setMessage('Please select a category.', true);
            setButtonState(submitButton, false, 'Add expense');
            return;
        }

        const payload = {
            category_id: selectedCategoryId,
            amount: Number(document.getElementById('amount').value),
            description: document.getElementById('description').value,
            date: document.getElementById('date').value,
            payment_method: document.getElementById('payment-method').value,
        };
        try {
            const response = await fetch('/api/expenses', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify(payload),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to save expense.');
            expenseForm.reset();
            document.getElementById('date').value = new Date().toISOString().split('T')[0];
            setMessage('Expense saved successfully.', false);
            currentOffset = 0;
            await fetchExpenses();
        } catch (error) {
            setMessage(error.message || 'Unable to save expense.', true);
        } finally {
            setButtonState(submitButton, false, 'Add expense');
        }
    });

    editForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const expenseId = document.getElementById('edit-expense-id').value;
        const selectedCategoryId = Number(editCategorySelect.value);
        if (!selectedCategoryId) {
            setMessage('Please select a category.', true);
            return;
        }
        const payload = {
            category_id: selectedCategoryId,
            amount: Number(document.getElementById('edit-amount').value),
            description: document.getElementById('edit-description').value,
            date: document.getElementById('edit-date').value,
            payment_method: document.getElementById('edit-payment-method').value,
        };
        try {
            const response = await fetch(`/api/expenses/${expenseId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify(payload),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to update expense.');
            editModal.hidden = true;
            setMessage('Expense updated successfully.', false);
            await fetchExpenses();
        } catch (error) {
            setMessage(error.message || 'Unable to update expense.', true);
        }
    });

    closeModalBtn.addEventListener('click', () => {
        editModal.hidden = true;
    });

    document.getElementById('delete-expense-btn').addEventListener('click', async () => {
        const expenseId = Number(document.getElementById('edit-expense-id').value);
        await deleteExpense(expenseId);
        editModal.hidden = true;
    });

    document.getElementById('expense-search').addEventListener('input', () => {
        currentOffset = 0;
        fetchExpenses();
    });
    expenseFilters.addEventListener('submit', (event) => {
        event.preventDefault();
        currentOffset = 0;
        expenseListMessage.classList.remove('error');
        fetchExpenses();
    });
    document.getElementById('clear-expense-filters').addEventListener('click', () => {
        expenseFilters.reset();
        currentOffset = 0;
        currentLimit = Number(pageSizeSelect.value);
        expenseListMessage.classList.remove('error');
        fetchExpenses();
    });
    document.getElementById('expense-sort').addEventListener('change', () => {
        currentOffset = 0;
        fetchExpenses();
    });
    pageSizeSelect.addEventListener('change', () => {
        currentLimit = Number(pageSizeSelect.value);
        currentOffset = 0;
        fetchExpenses();
    });
    previousPageButton.addEventListener('click', () => {
        currentOffset = Math.max(0, currentOffset - currentLimit);
        fetchExpenses();
    });
    nextPageButton.addEventListener('click', () => {
        currentOffset += currentLimit;
        fetchExpenses();
    });

    logoutButton.addEventListener('click', () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('expenseai_token');
        window.location.href = '/login';
    });

    // Set today's date as default
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('date').value = today;
    document.getElementById('edit-date').value = today;

    try {
        await loadProfile();
        await loadCategories();
        await fetchExpenses();
    } catch (error) {
        setMessage(error.message || 'Unable to load the expenses page.', true);
    }
});

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
