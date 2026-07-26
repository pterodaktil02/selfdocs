(() => {
    "use strict";

    const form = document.getElementById("order-form");
    if (!form) return;

    const clientFieldMap = {
        full_name: "client-full-name",
        short_name: "client-short-name",
        inn: "client-inn",
        kpp: "client-kpp",
        legal_address: "client-legal-address",
        bank_name: "client-bank-name",
        bank_account: "client-bank-account",
        bank_bik: "client-bank-bik",
        bank_corr_account: "client-bank-corr-account",
        contact_name: "client-contact-name",
        phone: "client-phone",
        email: "client-email",
        comment: "client-comment",
    };

    const selectedClientId = document.getElementById("selected-client-id");
    const clientUpdateChoice = document.getElementById("client-update-choice");
    const initialClientData = document.getElementById("selected-client-card-data");
    const nameInput = document.getElementById("client-full-name");
    const innInput = document.getElementById("client-inn");
    const nameSuggestions = document.getElementById("name-suggestions");
    const innSuggestions = document.getElementById("inn-suggestions");
    const itemsBody = document.getElementById("items-body");
    const orderTotal = document.getElementById("order-total");
    const startDate = form.querySelector('[name="work_start_date"]');
    const endDate = form.querySelector('[name="work_end_date"]');
    const dateChanged = document.getElementById("date-changed");

    let searchTimer = null;
    let requestSerial = 0;
    let fillingClient = false;
    let originalClientData = null;

    function normalized(value) {
        return String(value ?? "").trim();
    }

    function currentClientData() {
        const result = {};
        for (const [field, elementId] of Object.entries(clientFieldMap)) {
            const element = document.getElementById(elementId);
            result[field] = normalized(element?.value);
        }
        return result;
    }

    function clientDataChanged() {
        if (!selectedClientId.value || !originalClientData) return false;
        const current = currentClientData();
        return Object.keys(clientFieldMap).some(
            (field) => current[field] !== normalized(originalClientData[field])
        );
    }

    function clearClientUpdateChoice() {
        form.querySelectorAll('[name="client_update_mode"]').forEach((radio) => {
            radio.checked = false;
        });
    }

    function refreshClientUpdateChoice() {
        const changed = clientDataChanged();
        clientUpdateChoice.hidden = !changed;
        if (!changed) clearClientUpdateChoice();
    }

    function closeSuggestions() {
        for (const container of [nameSuggestions, innSuggestions]) {
            container.classList.remove("visible");
            container.replaceChildren();
        }
    }

    async function loadClient(clientId) {
        const response = await fetch(`/clients/api/${encodeURIComponent(clientId)}`, {
            headers: { Accept: "application/json" },
        });
        if (!response.ok) throw new Error("Не удалось загрузить заказчика.");
        const client = await response.json();
        fillingClient = true;
        try {
            for (const [field, elementId] of Object.entries(clientFieldMap)) {
                const element = document.getElementById(elementId);
                if (element) element.value = client[field] || "";
            }
            selectedClientId.value = String(client.id);
            originalClientData = {};
            for (const field of Object.keys(clientFieldMap)) {
                originalClientData[field] = normalized(client[field]);
            }
            clearClientUpdateChoice();
            refreshClientUpdateChoice();
        } finally {
            fillingClient = false;
        }
        closeSuggestions();
    }

    function suggestionButton(client) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "client-suggestion-item";
        const name = document.createElement("span");
        name.className = "client-suggestion-name";
        name.textContent = client.short_name || client.full_name || `Заказчик ${client.id}`;
        const details = document.createElement("span");
        details.className = "client-suggestion-details";
        const parts = [`ИНН ${client.inn || "—"}`];
        if (client.kpp) parts.push(`КПП ${client.kpp}`);
        details.textContent = parts.join(" · ");
        button.append(name, details);
        button.addEventListener("click", () => loadClient(client.id).catch((error) => alert(error.message)));
        return button;
    }

    function renderSuggestions(container, clients) {
        container.replaceChildren();
        if (!clients.length) {
            container.classList.remove("visible");
            return;
        }
        for (const client of clients) container.appendChild(suggestionButton(client));
        container.classList.add("visible");
    }

    async function searchClients(query, container) {
        const serial = ++requestSerial;
        const response = await fetch(`/clients/api/search?q=${encodeURIComponent(query)}`, {
            headers: { Accept: "application/json" },
        });
        if (!response.ok || serial !== requestSerial) return;
        renderSuggestions(container, await response.json());
    }

    function scheduleSearch(input, container, minimumLength) {
        clearTimeout(searchTimer);
        const query = input.value.trim();
        if (query.length < minimumLength) {
            container.classList.remove("visible");
            container.replaceChildren();
            return;
        }
        searchTimer = setTimeout(() => searchClients(query, container).catch(console.error), 180);
    }

    nameInput.addEventListener("input", () => {
        if (!fillingClient) scheduleSearch(nameInput, nameSuggestions, 2);
    });
    innInput.addEventListener("input", () => {
        if (!fillingClient) scheduleSearch(innInput, innSuggestions, 1);
    });
    for (const elementId of Object.values(clientFieldMap)) {
        document.getElementById(elementId)?.addEventListener("input", () => {
            if (!fillingClient) refreshClientUpdateChoice();
        });
    }
    document.addEventListener("click", (event) => {
        if (!nameSuggestions.contains(event.target) && event.target !== nameInput &&
            !innSuggestions.contains(event.target) && event.target !== innInput) closeSuggestions();
    });

    function parseNumber(value) {
        const number = Number(String(value || "").replace(/\s+/g, "").replace(",", "."));
        return Number.isFinite(number) ? number : 0;
    }
    function formatMoney(value) {
        return value.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    function rows() { return [...itemsBody.querySelectorAll(".item-row")]; }
    function rowEmpty(row) {
        return !row.querySelector('[name="item_description"]').value.trim() &&
               !row.querySelector('[name="item_price"]').value.trim();
    }
    function clearRow(row) {
        row.querySelector('[name="item_description"]').value = "";
        row.querySelector('[name="item_quantity"]').value = "1";
        // Единицу намеренно наследуем: позиции заказа обычно однородны.
        row.querySelector('[name="item_price"]').value = "";
        row.querySelector(".item-sum").textContent = "0,00";
    }
    function updateTotals() {
        let total = 0;
        for (const row of rows()) {
            const sum = parseNumber(row.querySelector('[name="item_quantity"]').value) *
                        parseNumber(row.querySelector('[name="item_price"]').value);
            row.querySelector(".item-sum").textContent = formatMoney(sum);
            total += sum;
        }
        orderTotal.textContent = formatMoney(total);
    }
    function updateRemoveButtons() {
        const allRows = rows();
        allRows.forEach((row, index) => {
            const button = row.querySelector(".remove-item");
            button.hidden = allRows.length === 1 || (index === allRows.length - 1 && rowEmpty(row));
        });
    }
    function ensureBlankLastRow() {
        const allRows = rows();
        if (!allRows.length) return;
        const last = allRows[allRows.length - 1];
        if (!rowEmpty(last)) {
            const clone = last.cloneNode(true);
            clearRow(clone);
            last.after(clone);
        }
        updateRemoveButtons();
        updateTotals();
    }

    itemsBody.addEventListener("input", (event) => {
        if (!event.target.matches("input, textarea")) return;
        updateTotals();
        if (event.target.closest(".item-row") === rows().at(-1)) ensureBlankLastRow();
        updateRemoveButtons();
    });
    itemsBody.addEventListener("click", (event) => {
        const button = event.target.closest(".remove-item");
        if (!button) return;
        if (rows().length > 1) button.closest(".item-row").remove();
        ensureBlankLastRow();
    });

    function normalizeDates(changed) {
        if (!startDate.value || !endDate.value) return;
        if (changed === "start" && endDate.value < startDate.value) endDate.value = startDate.value;
        if (changed === "end" && startDate.value > endDate.value) startDate.value = endDate.value;
        dateChanged.value = changed;
    }
    startDate.addEventListener("change", () => normalizeDates("start"));
    endDate.addEventListener("change", () => normalizeDates("end"));

    form.addEventListener("submit", (event) => {
        if (!clientDataChanged()) return;
        if (form.querySelector('[name="client_update_mode"]:checked')) return;
        event.preventDefault();
        clientUpdateChoice.hidden = false;
        clientUpdateChoice.scrollIntoView({ behavior: "smooth", block: "center" });
        alert("Выбери: обновить карточку заказчика или использовать изменения только в этом заказе.");
    });

    try {
        const parsed = JSON.parse(initialClientData?.textContent || "{}");
        if (selectedClientId.value && parsed && Object.keys(parsed).length) {
            originalClientData = parsed;
        }
    } catch (error) {
        console.error("Не удалось прочитать исходные реквизиты заказчика", error);
    }

    refreshClientUpdateChoice();
    ensureBlankLastRow();
})();
