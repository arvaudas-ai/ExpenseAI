document.addEventListener('DOMContentLoaded', async () => {
    const currentPath = window.location.pathname;
    document.querySelectorAll('.app-nav a').forEach((link) => {
        link.classList.toggle('active', link.getAttribute('href') === currentPath);
    });
    const pageTitle = document.getElementById('page-title');
    if (pageTitle && currentPath === '/analytics') pageTitle.textContent = 'Analytics';
    const welcome = document.getElementById('welcome-message');
    const logoutBtn = document.getElementById('logout-btn');
    const message = document.getElementById('dashboard-message');
    const filterForm = document.getElementById('analytics-filters');
    const clearFiltersButton = document.getElementById('clear-filters-btn');
    const exportButton = document.getElementById('export-csv-btn');
    const runAnalysisButton = document.getElementById('run-analysis-btn');
    const analysisMessage = document.getElementById('analysis-message');
    const analysisResults = document.getElementById('analysis-results');
    const budgetForm = document.getElementById('budget-form');
    const budgetList = document.getElementById('budget-list');
    const budgetMessage = document.getElementById('budget-message');
    const budgetOverviewMessage = document.getElementById('budget-overview-message');
    const budgetNameInput = document.getElementById('budget-name');
    const budgetAmountInput = document.getElementById('budget-amount');
    const budgetCategorySelect = document.getElementById('budget-category');
    const saveBudgetButton = document.getElementById('save-budget-btn');
    const cancelBudgetEditButton = document.getElementById('cancel-budget-edit');
    let editingBudgetId = null;

    if (!welcome || !logoutBtn || !message) return;

    const token = localStorage.getItem('access_token') || localStorage.getItem('expenseai_token');
    if (!token) {
        window.location.href = '/login';
        return;
    }

    const iconMap = {
        food: '🍔', transport: '🚗', utilities: '💡', entertainment: '🎬', shopping: '🛍️',
        health: '⚕️', education: '📚', travel: '✈️', dining: '🍽️', groceries: '🛒',
        gas: '⛽', electricity: '⚡', water: '💧', internet: '📶', phone: '📱', movie: '🎥',
        music: '🎵', books: '📖', sports: '⚽', gym: '🏋️', medical: '🏥', pharmacy: '💊',
        doctor: '👨‍⚕️', school: '🎓', tuition: '🎓', plane: '✈️', hotel: '🏨', taxi: '🚕', other: '📌'
    };

    const setMessage = (text, isError = false) => {
        message.textContent = text;
        message.classList.toggle('error', isError);
        message.classList.toggle('success', Boolean(text) && !isError);
    };

    const formatCurrency = (amount, currency) => {
        try {
            return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount);
        } catch (error) {
            return `${currency} ${Number(amount).toFixed(2)}`;
        }
    };

    let currentCurrency = 'USD';
    const chartPalette = ['#b69acd', '#d6aebb', '#a9c690', '#d6b08b', '#cc929c', '#9b8aa8', '#86a89a'];

    const queryString = () => {
        const params = new URLSearchParams();
        const startDate = document.getElementById('start-date').value;
        const endDate = document.getElementById('end-date').value;
        const categoryId = document.getElementById('filter-category').value;
        const paymentMethod = document.getElementById('filter-payment').value;
        if (startDate) params.set('start_date', startDate);
        if (endDate) params.set('end_date', endDate);
        if (categoryId) params.set('category_id', categoryId);
        if (paymentMethod) params.set('payment_method', paymentMethod);
        return params;
    };

    const setBudgetMessage = (text = '', isError = false) => {
        budgetMessage.textContent = text;
        budgetMessage.classList.toggle('error', Boolean(text) && isError);
        budgetMessage.classList.toggle('success', Boolean(text) && !isError);
    };

    const resetBudgetForm = () => {
        editingBudgetId = null;
        budgetForm.reset();
        saveBudgetButton.textContent = 'Add budget';
        cancelBudgetEditButton.hidden = true;
    };

    const loadBudgets = async () => {
        budgetList.replaceChildren(Object.assign(document.createElement('p'), {
            className: 'empty-state',
            textContent: 'Loading budgets...',
        }));
        const response = await fetch('/api/budgets', { headers: { Authorization: `Bearer ${token}` } });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to load budgets.');
        renderBudgets(data);
    };

    const renderBudgets = (budgets) => {
        const overCount = budgets.filter((budget) => budget.status === 'over').length;
        const nearCount = budgets.filter((budget) => budget.status === 'near').length;
        budgetOverviewMessage.hidden = budgets.length === 0;
        budgetOverviewMessage.classList.remove('error', 'warning', 'success');
        if (overCount) {
            budgetOverviewMessage.classList.add('error');
            budgetOverviewMessage.textContent = `${overCount} budget${overCount === 1 ? ' is' : 's are'} over the limit. Review spending or adjust the budget.`;
        } else if (nearCount) {
            budgetOverviewMessage.classList.add('warning');
            budgetOverviewMessage.textContent = `${nearCount} budget${nearCount === 1 ? ' is' : 's are'} nearing its limit.`;
        } else if (budgets.length) {
            budgetOverviewMessage.classList.add('success');
            budgetOverviewMessage.textContent = 'All budgets are currently under their limits.';
        }
        if (!budgets.length) {
            budgetList.replaceChildren(Object.assign(document.createElement('p'), {
                className: 'empty-state',
                textContent: 'No budgets yet. Set a monthly limit to track your progress.',
            }));
            return;
        }
        const fragment = document.createDocumentFragment();
        budgets.forEach((budget) => {
            const card = document.createElement('article');
            card.className = `budget-card budget-status-${budget.status}`;
            const heading = document.createElement('div');
            heading.className = 'budget-card-heading';
            const titleWrap = document.createElement('div');
            const title = document.createElement('h3');
            title.textContent = budget.name;
            const scope = document.createElement('p');
            scope.textContent = `${budget.category_name} · ${budget.period_start} to ${budget.period_end}`;
            titleWrap.append(title, scope);
            const status = document.createElement('span');
            status.className = `budget-status-label status-${budget.status}`;
            status.textContent = budget.status === 'over' ? 'Over budget' : budget.status === 'near' ? 'Near limit' : 'On track';
            heading.append(titleWrap, status);

            const totals = document.createElement('div');
            totals.className = 'budget-totals';
            const spent = document.createElement('strong');
            spent.textContent = `${formatCurrency(budget.spent, currentCurrency)} spent`;
            const remaining = document.createElement('span');
            remaining.textContent = `${formatCurrency(Math.abs(budget.remaining), currentCurrency)} ${budget.remaining < 0 ? 'over' : 'remaining'} of ${formatCurrency(budget.amount, currentCurrency)}`;
            totals.append(spent, remaining);

            const progress = document.createElement('div');
            progress.className = 'budget-progress-track';
            progress.setAttribute('role', 'progressbar');
            progress.setAttribute('aria-label', `${budget.name} budget used`);
            progress.setAttribute('aria-valuemin', '0');
            progress.setAttribute('aria-valuemax', '100');
            progress.setAttribute('aria-valuenow', String(Math.min(100, budget.percent_used)));
            const fill = document.createElement('span');
            fill.style.width = `${Math.min(100, budget.percent_used)}%`;
            progress.appendChild(fill);
            const percent = document.createElement('span');
            percent.className = 'budget-percent';
            percent.textContent = `${budget.percent_used}% used`;

            const actions = document.createElement('div');
            actions.className = 'budget-actions';
            const editButton = document.createElement('button');
            editButton.type = 'button';
            editButton.className = 'secondary';
            editButton.textContent = 'Edit';
            editButton.addEventListener('click', () => {
                editingBudgetId = budget.id;
                budgetNameInput.value = budget.name;
                budgetAmountInput.value = budget.amount;
                budgetCategorySelect.value = budget.category_id || '';
                saveBudgetButton.textContent = 'Save budget';
                cancelBudgetEditButton.hidden = false;
                budgetNameInput.focus();
            });
            const deleteButton = document.createElement('button');
            deleteButton.type = 'button';
            deleteButton.className = 'danger';
            deleteButton.textContent = 'Delete';
            deleteButton.addEventListener('click', async () => {
                if (!window.confirm(`Delete the ${budget.name} budget?`)) return;
                try {
                    const deleted = await fetch(`/api/budgets/${budget.id}`, {
                        method: 'DELETE',
                        headers: { Authorization: `Bearer ${token}` },
                    });
                    if (!deleted.ok && deleted.status !== 204) {
                        const error = await deleted.json().catch(() => ({}));
                        throw new Error(typeof error.detail === 'string' ? error.detail : 'Unable to delete budget.');
                    }
                    if (editingBudgetId === budget.id) resetBudgetForm();
                    setBudgetMessage('Budget deleted.', false);
                    await loadBudgets();
                } catch (error) {
                    setBudgetMessage(error.message || 'Unable to delete budget.', true);
                }
            });
            actions.append(editButton, deleteButton);
            card.append(heading, totals, progress, percent, actions);
            fragment.appendChild(card);
        });
        budgetList.replaceChildren(fragment);
    };

    const chartState = (text, state) => {
        const element = document.createElement('p');
        element.className = `chart-state chart-state-${state}`;
        element.textContent = text;
        return element;
    };

    const svgElement = (name, attributes = {}) => {
        const element = document.createElementNS('http://www.w3.org/2000/svg', name);
        Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
        return element;
    };

    const renderMonthlyChart = (months, format) => {
        const container = document.getElementById('monthly-chart');
        if (!months.length) {
            container.replaceChildren(chartState('No monthly data matches these filters.', 'empty'));
            return;
        }

        const width = Math.max(720, months.length * 84);
        const height = 270;
        const left = 76;
        const right = width - 24;
        const top = 20;
        const bottom = height - 48;
        const maxTotal = Math.max(...months.map((month) => month.total), 1);
        const svg = svgElement('svg', {
            viewBox: `0 0 ${width} ${height}`,
            width,
            height,
            role: 'img',
            'aria-label': `Monthly spending line chart, amounts in ${currentCurrency}`,
        });
        const points = months.map((month, index) => ({
            month,
            x: months.length === 1 ? (left + right) / 2 : left + (index * (right - left)) / (months.length - 1),
            y: bottom - (month.total / maxTotal) * (bottom - top),
        }));

        for (let gridIndex = 0; gridIndex <= 4; gridIndex += 1) {
            const y = top + ((bottom - top) * gridIndex) / 4;
            const amount = maxTotal * (1 - gridIndex / 4);
            svg.appendChild(svgElement('line', { x1: left, x2: right, y1: y, y2: y, class: 'chart-grid-line' }));
            const tick = svgElement('text', { x: left - 10, y: y + 4, 'text-anchor': 'end', class: 'chart-axis-label' });
            tick.textContent = format(amount);
            svg.appendChild(tick);
        }

        const pathData = points.map((point, index) => `${index ? 'L' : 'M'} ${point.x} ${point.y}`).join(' ');
        svg.appendChild(svgElement('path', { d: pathData, class: 'trend-line' }));
        points.forEach(({ month, x, y }) => {
            const point = svgElement('circle', { cx: x, cy: y, r: 5, class: 'trend-point', tabindex: 0 });
            const title = svgElement('title');
            title.textContent = `${month.label}: ${format(month.total)}, ${month.expense_count} expense${month.expense_count === 1 ? '' : 's'}`;
            point.appendChild(title);
            svg.appendChild(point);
            const label = svgElement('text', { x, y: bottom + 26, 'text-anchor': 'middle', class: 'chart-axis-label' });
            label.textContent = month.label;
            svg.appendChild(label);
        });

        container.replaceChildren(svg);
    };

    const renderCategoryDonut = (categories, format, totalSpending) => {
        const container = document.getElementById('category-donut');
        if (!categories.length || totalSpending <= 0) {
            container.replaceChildren(chartState('No category data matches these filters.', 'empty'));
            return;
        }

        const svg = svgElement('svg', { viewBox: '0 0 220 220', role: 'img', 'aria-label': `Category spending distribution in ${currentCurrency}` });
        const radius = 74;
        const circumference = 2 * Math.PI * radius;
        let offset = 0;
        categories.forEach((category, index) => {
            const segmentColor = chartPalette[index % chartPalette.length];
            const segment = (category.total / totalSpending) * circumference;
            const ring = svgElement('circle', {
                cx: 110,
                cy: 110,
                r: radius,
                fill: 'none',
                stroke: segmentColor,
                'stroke-width': 30,
                'stroke-dasharray': `${segment} ${circumference - segment}`,
                'stroke-dashoffset': -offset,
                transform: 'rotate(-90 110 110)',
                class: 'donut-segment',
            });
            const title = svgElement('title');
            title.textContent = `${category.name}: ${format(category.total)} (${Math.round((category.total / totalSpending) * 100)}%)`;
            ring.appendChild(title);
            svg.appendChild(ring);
            offset += segment;
        });

        const totalLabel = svgElement('text', { x: 110, y: 105, 'text-anchor': 'middle', class: 'donut-total' });
        totalLabel.textContent = format(totalSpending);
        const caption = svgElement('text', { x: 110, y: 128, 'text-anchor': 'middle', class: 'donut-caption' });
        caption.textContent = 'total spending';
        svg.append(totalLabel, caption);
        container.replaceChildren(svg);
    };

    const renderPaymentChart = (methods, format, totalSpending) => {
        const container = document.getElementById('payment-chart');
        if (!methods.length || totalSpending <= 0) {
            container.replaceChildren(chartState('No payment-method data matches these filters.', 'empty'));
            return;
        }

        const labels = {
            cash: 'Cash', credit_card: 'Credit card', debit_card: 'Debit card',
            bank_transfer: 'Bank transfer', digital_wallet: 'Digital wallet', other: 'Other',
        };
        const fragment = document.createDocumentFragment();
        methods.forEach((method, index) => {
            const row = document.createElement('div');
            row.className = 'payment-row';
            const heading = document.createElement('div');
            heading.className = 'payment-row-heading';
            const label = document.createElement('strong');
            label.textContent = labels[method.payment_method] || method.payment_method;
            const amount = document.createElement('span');
            amount.textContent = `${format(method.total)} · ${method.expense_count} expense${method.expense_count === 1 ? '' : 's'}`;
            heading.append(label, amount);
            const track = document.createElement('div');
            track.className = 'payment-bar-track';
            const bar = document.createElement('span');
            bar.style.width = `${Math.min(100, (method.total / totalSpending) * 100)}%`;
            bar.style.backgroundColor = chartPalette[index % chartPalette.length];
            track.appendChild(bar);
            row.append(heading, track);
            fragment.appendChild(row);
        });
        container.replaceChildren(fragment);
    };

    const renderCategories = (categories, format, totalSpending) => {
        const container = document.getElementById('category-breakdown');
        if (!categories.length) {
            container.innerHTML = '<p class="empty-state">Add an expense to see your spending split.</p>';
            return;
        }
        container.innerHTML = categories.map((category, index) => {
            const percentage = totalSpending ? Math.round((category.total / totalSpending) * 100) : 0;
            const seriesColor = chartPalette[index % chartPalette.length];
            return `
                <div class="category-row">
                    <div class="category-row-heading">
                        <span class="category-name"><span class="category-dot" style="background:${seriesColor}"></span>${iconMap[category.icon] || iconMap.other} ${escapeHtml(category.name)}</span>
                        <strong>${format(category.total)}</strong>
                    </div>
                    <div class="category-progress"><span style="width:${percentage}%; background:${seriesColor}"></span></div>
                    <span class="category-meta">${percentage}% of total</span>
                </div>
            `;
        }).join('');
    };

    const renderRecentExpenses = (expenses, format) => {
        const container = document.getElementById('recent-expenses');
        if (!expenses.length) {
            container.innerHTML = '<p class="empty-state">No expenses recorded yet. Your recent activity will appear here.</p>';
            return;
        }
        container.innerHTML = expenses.map((expense) => {
            const category = expense.category || { name: 'Uncategorized', icon: 'other', color: '#95A5A6' };
            return `
                <a class="recent-expense" href="/expenses">
                    <span class="recent-icon" style="background:${category.color}22; color:${category.color}">${iconMap[category.icon] || iconMap.other}</span>
                    <span class="recent-details"><strong>${escapeHtml(expense.description)}</strong><small>${escapeHtml(category.name)} · ${expense.date}</small></span>
                    <strong class="recent-amount">${format(expense.amount)}</strong>
                </a>
            `;
        }).join('');
    };

    const renderHighestExpenses = (expenses, format) => {
        const container = document.getElementById('highest-expenses');
        if (!expenses.length) {
            container.innerHTML = '<p class="empty-state">No expenses match the current filters.</p>';
            return;
        }
        container.innerHTML = expenses.map((expense) => {
            const category = expense.category || { name: 'Uncategorized', icon: 'other', color: '#95A5A6' };
            return `<div class="recent-expense"><span class="recent-icon" style="background:${category.color}22; color:${category.color}">${iconMap[category.icon] || iconMap.other}</span><span class="recent-details"><strong>${escapeHtml(expense.description)}</strong><small>${escapeHtml(category.name)} · ${expense.date}</small></span><strong class="recent-amount">${format(expense.amount)}</strong></div>`;
        }).join('');
    };

    const renderInsights = (insights) => {
        document.getElementById('insight-category').textContent = insights.highest_spending_category || 'None yet';
        document.getElementById('insight-month').textContent = insights.highest_spending_month || 'None yet';
        const change = insights.month_over_month_change_percent;
        document.getElementById('insight-change').textContent = change === null ? 'Not enough data' : `${change > 0 ? '+' : ''}${change}%`;
    };

    const renderAnalysis = (result) => {
        analysisResults.replaceChildren();
        const narrative = document.createElement('p');
        narrative.className = 'analysis-narrative';
        narrative.textContent = result.analysis;
        analysisResults.appendChild(narrative);

        const stats = result.stats;
        const category = stats.category_totals[0];
        const monthChange = stats.month_over_month.change_percent;
        const facts = document.createElement('div');
        facts.className = 'analysis-facts';
        const factItems = [
            ['Tracked total', formatCurrency(stats.total_spending, result.currency)],
            ['Expenses', String(stats.expense_count)],
            ['Average expense', formatCurrency(stats.average_expense, result.currency)],
            ['Top category', category ? `${category.category} (${category.share_percent}%)` : 'No category data'],
            ['Month change', monthChange === null ? 'Not enough previous-month data' : `${monthChange > 0 ? '+' : ''}${monthChange}%`],
            ['Current-month spike', stats.current_month_spike ? `${stats.current_month_spike.multiple_of_average}× prior active-month average` : 'None detected'],
            ['Recurring-looking groups', String(stats.recurring_patterns.length)],
        ];
        factItems.forEach(([labelText, valueText]) => {
            const item = document.createElement('div');
            item.className = 'analysis-fact';
            const label = document.createElement('span');
            label.textContent = labelText;
            const value = document.createElement('strong');
            value.textContent = valueText;
            item.append(label, value);
            facts.appendChild(item);
        });
        analysisResults.appendChild(facts);
        analysisMessage.textContent = result.insufficient_data
            ? 'Limited history: figures are shown, but there is not enough data for reliable pattern detection.'
            : '';
        analysisMessage.classList.remove('error');
    };

    const runSpendingAnalysis = async () => {
        runAnalysisButton.disabled = true;
        runAnalysisButton.textContent = 'Analyzing...';
        analysisMessage.textContent = '';
        analysisMessage.classList.remove('error');
        analysisResults.replaceChildren(Object.assign(document.createElement('p'), {
            className: 'chart-state chart-state-loading',
            textContent: 'Calculating your spending patterns...',
        }));
        try {
            const response = await fetch('/api/analysis/spending', {
                headers: { Authorization: `Bearer ${token}` },
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                const error = new Error(typeof data.detail === 'string' ? data.detail : 'Unable to analyze spending.');
                error.status = response.status;
                throw error;
            }
            renderAnalysis(data);
        } catch (error) {
            const rateLimited = error?.status === 429;
            analysisResults.replaceChildren(Object.assign(document.createElement('p'), {
                className: `chart-state chart-state-${rateLimited ? 'warning' : 'error'}`,
                textContent: error.message || 'Unable to analyze spending.',
            }));
            analysisMessage.textContent = error.message || 'Unable to analyze spending.';
            analysisMessage.classList.add(rateLimited ? 'warning' : 'error');
        } finally {
            runAnalysisButton.disabled = false;
            runAnalysisButton.textContent = 'Analyze again';
        }
    };

    const loadCategories = async () => {
        const response = await fetch('/api/categories', { headers: { Authorization: `Bearer ${token}` } });
        const data = await response.json().catch(() => []);
        if (!response.ok) throw new Error('Unable to load categories.');
        const optionList = '<option value="">All categories</option>' + data.map((category) => `<option value="${category.id}">${escapeHtml(category.name)}</option>`).join('');
        document.getElementById('filter-category').innerHTML = optionList;
        budgetCategorySelect.innerHTML = '<option value="">Overall spending</option>' + data.map((category) => `<option value="${category.id}">${escapeHtml(category.name)}</option>`).join('');
    };

    const loadSummary = async (currency) => {
        setChartLoading();
        const response = await fetch(`/api/dashboard/summary?${queryString().toString()}`, {
            headers: { Authorization: `Bearer ${token}` },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to load dashboard.');
        }

        const format = (amount) => formatCurrency(amount, currency);
        document.getElementById('total-spending').textContent = format(data.total_spending);
        document.getElementById('expense-count').textContent = data.expense_count;

        const topCategory = data.spending_by_category[0];
        document.getElementById('top-category').textContent = topCategory ? topCategory.name : 'None yet';
        document.getElementById('top-category-total').textContent = topCategory
            ? `${format(topCategory.total)} across ${topCategory.expense_count} expense${topCategory.expense_count === 1 ? '' : 's'}`
            : 'No spending yet';

        const sixMonthTotal = data.monthly_spending.reduce((sum, month) => sum + month.total, 0);
        document.getElementById('trend-total').textContent = `${format(sixMonthTotal)} in six months`;
        renderMonthlyChart(data.monthly_spending, format);
        renderCategoryDonut(data.spending_by_category, format, data.total_spending);
        renderCategories(data.spending_by_category, format, data.total_spending);
        renderPaymentChart(data.payment_method_spending, format, data.total_spending);
        renderRecentExpenses(data.recent_expenses, format);
        renderHighestExpenses(data.highest_expenses, format);
        renderInsights(data.insights);
    };

    try {
        const response = await fetch('/api/auth/me', {
            headers: { Authorization: `Bearer ${token}` },
        });

        if (!response.ok) {
            localStorage.removeItem('access_token');
            localStorage.removeItem('expenseai_token');
            window.location.href = '/login';
            return;
        }

        const data = await response.json();
        welcome.textContent = `Welcome, ${data.name}!`;
        currentCurrency = data.currency || 'USD';
        await loadCategories();
        await loadSummary(currentCurrency);
        await loadBudgets();
    } catch (error) {
        setMessage(error.message || 'Unable to load dashboard.', true);
        setBudgetMessage(error.message || 'Unable to load budgets.', true);
    }

    logoutBtn.addEventListener('click', () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('expenseai_token');
        window.location.href = '/login';
    });

    filterForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const startDate = document.getElementById('start-date').value;
        const endDate = document.getElementById('end-date').value;
        if (startDate && endDate && startDate > endDate) {
            setMessage('The start date must be on or before the end date.', true);
            return;
        }
        setMessage('');
        try {
            await loadSummary(currentCurrency);
        } catch (error) {
            setChartsError(error.message || 'Unable to apply filters.');
            setMessage(error.message || 'Unable to apply filters.', true);
        }
    });

    clearFiltersButton.addEventListener('click', async () => {
        filterForm.reset();
        setMessage('');
        try {
            await loadSummary(currentCurrency);
        } catch (error) {
            setChartsError(error.message || 'Unable to clear filters.');
            setMessage(error.message || 'Unable to clear filters.', true);
        }
    });

    exportButton.addEventListener('click', async () => {
        try {
            const response = await fetch(`/api/dashboard/export.csv?${queryString().toString()}`, { headers: { Authorization: `Bearer ${token}` } });
            if (!response.ok) throw new Error('Unable to export expenses.');
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = 'expenseai-expenses.csv';
            link.click();
            URL.revokeObjectURL(url);
        } catch (error) {
            setMessage(error.message || 'Unable to export expenses.', true);
        }
    });

    runAnalysisButton.addEventListener('click', runSpendingAnalysis);

    budgetForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const payload = {
            name: budgetNameInput.value.trim(),
            amount: Number(budgetAmountInput.value),
            period: 'monthly',
            category_id: budgetCategorySelect.value ? Number(budgetCategorySelect.value) : null,
        };
        if (!payload.name || !Number.isFinite(payload.amount) || payload.amount <= 0) {
            setBudgetMessage('Enter a budget name and a positive monthly limit.', true);
            return;
        }
        saveBudgetButton.disabled = true;
        try {
            const response = await fetch(editingBudgetId ? `/api/budgets/${editingBudgetId}` : '/api/budgets', {
                method: editingBudgetId ? 'PUT' : 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify(payload),
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Unable to save budget.');
            resetBudgetForm();
            setBudgetMessage('Budget saved.', false);
            await loadBudgets();
        } catch (error) {
            setBudgetMessage(error.message || 'Unable to save budget.', true);
        } finally {
            saveBudgetButton.disabled = false;
        }
    });

    cancelBudgetEditButton.addEventListener('click', resetBudgetForm);

    function setChartLoading() {
        ['monthly-chart', 'category-donut', 'category-breakdown', 'payment-chart'].forEach((id) => {
            const container = document.getElementById(id);
            if (container) {
                container.replaceChildren(Object.assign(document.createElement('p'), {
                    className: 'chart-state chart-state-loading',
                    textContent: 'Loading chart data...',
                }));
            }
        });
    }

    function setChartsError(text) {
        ['monthly-chart', 'category-donut', 'category-breakdown', 'payment-chart'].forEach((id) => {
            const container = document.getElementById(id);
            if (container) {
                const state = document.createElement('p');
                state.className = 'chart-state chart-state-error';
                state.textContent = text;
                container.replaceChildren(state);
            }
        });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});
