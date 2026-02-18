// ============================================================
// Hindi Song Lyric Generator
// Generates random Hindi lyrics based on mood and structure
// ============================================================

const vocabulary = {
    romantic: {
        subjects: [
            'tere naina', 'teri hansi', 'tere hoth', 'tera chehra',
            'teri yaadein', 'tera saath', 'teri baahein', 'tera pyaar',
            'tere sapne', 'teri zulfein', 'tera ishq', 'teri aahat'
        ],
        verbs: [
            'mujhe bula rahe hain', 'dil mein bas gaye', 'mujhko le gaye',
            'mera dil churaya', 'nasha kar gaye', 'mujhe jagaya',
            'dil ko chhu liya', 'aankhon mein sama gaye', 'dhadkan ban gaye',
            'mujhko pagal kiya', 'chain chura liya', 'jeena sikha diya'
        ],
        phrases: [
            'ishq tera mera', 'dil ki dhadkan mein', 'pyaar ki raahon mein',
            'chaandni raat mein', 'sapnon ke shehar mein', 'dil se dil tak',
            'lamhon ki barishon mein', 'khushiyon ke mausam mein',
            'hothon pe tera naam hai', 'aankhon mein tera jahan hai',
            'dil mein teri tasveer hai', 'saanson mein teri khushbu hai'
        ],
        hooks: [
            'Tujhe dekha toh jaana sanam',
            'Dil ke taar se bajti hai teri dhun',
            'Tu hi mera sapna, tu hi meri manzil',
            'Ishq mein hum tumhein kya bataayein',
            'Tera chehra jaise chaand sitaaron mein',
            'Pyaar ki yeh kaisi daastaan hai',
            'Dil ne dil se kya keh diya',
            'Tere bina yeh dil udaas hai'
        ],
        imagery: [
            'chaandni bikhri hai raaton mein',
            'phool khile hain baagon mein',
            'sitaare hamare gawah hain',
            'baarish ki boondein gaati hain',
            'hawa mein ghulta tera pyaar',
            'nadi kinare teri yaad aaye'
        ],
        endLines: [
            'bas tera hi saath chahiye mujhe',
            'tere bina kuch bhi nahi',
            'tu hi meri duniya hai',
            'har pal tera intezaar hai',
            'dil ye tera deewana hai',
            'tera hi hoon main, sirf tera'
        ]
    },

    sad: {
        subjects: [
            'yeh tanhai', 'yeh aansu', 'bikhra safar', 'sooni raahein',
            'tuti saansein', 'geeli palken', 'khamoshi', 'yeh dard',
            'yeh judai', 'toota dil', 'bujhti shaam', 'sunaapan'
        ],
        verbs: [
            'rula deti hai', 'tadpata hai', 'satata hai',
            'jeene nahi deta', 'chain nahi aata', 'neend chura leta hai',
            'dil ko jalata hai', 'yaad dilata hai', 'aur rota hai',
            'rone ko majboor karta hai', 'sukoon cheen leta hai', 'dard deta hai'
        ],
        phrases: [
            'koi nahi mera yahaan', 'akela chhod diya tune',
            'kyun kiya aisa mere saath', 'toota hua dil',
            'sooni raaton mein jaagta hoon', 'ansoo ruk-te nahi',
            'har khushi door ho gayi', 'zindagi ne dhoka diya',
            'kyun bichhad gaye hum', 'woh din yaad aate hain',
            'kaash waqt laut aata', 'dil ke tukde hazaar hue'
        ],
        hooks: [
            'Tanhaaiyaan meri saathi ban gayi',
            'Ro raha hai dil, sun le zara',
            'Khamoshiyon mein dooba yeh jahaan',
            'Bichhad ke tujhse kho gaya main',
            'Yeh dard kaise sah loon main',
            'Kyun chala gaya tu door mujhse',
            'Aansu palkon pe ruk nahi paate',
            'Sooni raaton mein tera gham hai'
        ],
        imagery: [
            'suraj bhi chhup gaya baadlon mein',
            'patjhad ka mausam aa gaya',
            'kaali raaten lambi hoti hain',
            'baarish aansuon jaisi girti hai',
            'sukhey phool yaad dilate hain',
            'khamosh hawa bhi ro rahi hai'
        ],
        endLines: [
            'ab koi sahara nahi raha',
            'dil toota hai, jud nahi sakta',
            'tanhaaiyaan hi meri kismat hain',
            'yeh dard mera khatam nahi hota',
            'kho gaya sab kuch, kuch nahi bacha',
            'bas rona hi meri taqdeer hai'
        ]
    },

    happy: {
        subjects: [
            'yeh khushi', 'yeh masti', 'nayi subah', 'rang birangi duniya',
            'khilta hua din', 'nachti hawa', 'gungunata mann',
            'yeh jashn', 'chamakti dhoop', 'hansti zindagi'
        ],
        verbs: [
            'nachne ko bole', 'gaane ko kahe', 'jhoomne ko kahe',
            'dil ko khush kar de', 'muskurane ko kahe', 'udne ko kahe',
            'celebrate karo', 'nachte raho', 'gungunao saathi',
            'khushiyan manaao', 'duniya rangeen kar do', 'masti karo'
        ],
        phrases: [
            'aaj ki raat rang jamayein', 'duniya bhar ki khushi yahaan hai',
            'nachte gaate chalein hum', 'zindagi ek jashn hai',
            'har pal mein khushi hai', 'rang udaayein aaj hum',
            'muskurao toh sahi', 'chhod do saari chinta',
            'paon tham-te nahi aaj', 'dil garden garden hai',
            'khushiyon ka mausam aaya hai', 'aaj ki party meri taraf se'
        ],
        hooks: [
            'Aaj ki raat hum nachein saari raat',
            'Khushi ke rang bikhre hain charon taraf',
            'Zindagi mein aaya naya mausam',
            'Dil karta hai nachoon gaoon',
            'Chal hawaon ke saath ud chalein',
            'Aaj toh party hogi boss',
            'Masti mein jhoomein duniya bhool ke',
            'Badal pe paon hai aaj mere'
        ],
        imagery: [
            'titliyan nach rahi hain phoolon pe',
            'indradhanush rang bikher raha hai',
            'dhoop mein chamak rahi duniya',
            'hawa mein udti patangein',
            'baarish mein nachte bache',
            'subah ki pehli kiran muskuraaye'
        ],
        endLines: [
            'aaj ki raat mast hai',
            'zindagi beautiful hai bhai',
            'nachte raho, gaate raho',
            'khush raho, mast raho',
            'yeh waqt phir nahi aayega',
            'chalein duniya ghoomne saath saath'
        ]
    },

    devotional: {
        subjects: [
            'hey prabhu', 'hey bhagwan', 'mere maula',
            'hey ishwar', 'hey daata', 'mere ram',
            'hey krishna', 'mere malik', 'hey shiv shankar',
            'hey mata rani', 'hey govind', 'mere murlidhar'
        ],
        verbs: [
            'mujhpe kripa karo', 'meri sun lo', 'darshan do',
            'raah dikhao', 'sahara do mujhe', 'apnaao mujhe',
            'mujhe shakti do', 'meri raksha karo', 'aashirwaad do',
            'mujhe taar do', 'meri bhakti sweekar karo', 'mujhpe daya karo'
        ],
        phrases: [
            'teri sharan mein aaya hoon', 'tu hi sahara mera',
            'tere bina koi nahi mera', 'tere charno mein sir jhukaya',
            'mann ki mala japte hain', 'bhakti mein dooba mann',
            'tu hi raah dikhane wala', 'teri leela nyaari hai',
            'tera naam hi sukoon hai', 'tere dar pe aaya hoon',
            'tu antaryaami sab jaane', 'tera jas gaayein hum'
        ],
        hooks: [
            'Tera naam leke subah hoti hai',
            'Tu hi mera sahara hai prabhu',
            'Bhakti mein mila hai sukoon mujhe',
            'Tere charno mein hai meri duniya',
            'Mann mein basa le tujhe sajna',
            'Jai jai kaar teri hoti rahe',
            'Teri mahima nyaari hai prabhu',
            'Tere dar pe jhuka hai mera sir'
        ],
        imagery: [
            'mandir ki ghanti goonj rahi hai',
            'deepak jal raha andheron mein',
            'ganga ki dhara pavitra beh rahi',
            'phool charno mein arpan hain',
            'dhoop batti ki khushbu pheli hai',
            'aarti ki lau roshan hai'
        ],
        endLines: [
            'tera hi tera naam japte hain',
            'tere charno mein hee meri mukti hai',
            'tu hi mera sab kuch hai prabhu',
            'teri kripa bani rahe hum par',
            'har saans mein tera naam hai',
            'tere bina yeh jeevan soona hai'
        ]
    },

    patriotic: {
        subjects: [
            'meri mitti', 'yeh dharti', 'mera Hindustan', 'tiranga pyaara',
            'mera watan', 'yeh desh', 'veer jawaan', 'maa Bharat',
            'himalaya', 'ganga yamuna', 'hindustan ki mitti', 'desh ki shaan'
        ],
        verbs: [
            'garv se seena chauda karo', 'namaskar karo', 'sar jhukao',
            'salaam karo', 'rakhwali karo', 'izzat badhaao',
            'himmat mat haaro', 'himmat se lado', 'josh mein aao',
            'apni pehchaan banaao', 'dushmanon ko bhagaao', 'desh seva karo'
        ],
        phrases: [
            'vande maataram gaayein hum', 'shaheedon ko naman hai',
            'yeh dharti maa hai hamari', 'jhanda ooncha rahe hamara',
            'har ghar tiranga lehraaye', 'desh ke liye jaan de dein',
            'ek hain hum, ek hain hum', 'hindustan zindabaad',
            'mitti ki khushbu pyaari hai', 'desh prem hi dharma hai',
            'veeron ki gatha gaayein hum', 'aazadi ki yeh kahani hai'
        ],
        hooks: [
            'Mera desh mahaan, meri shaan mahaan',
            'Hindustan ki mitti se pyaara kuch nahi',
            'Jhanda ooncha rahe hamara, sada yeh naara ho',
            'Vatan ke liye jee bhi dein, mar bhi dein',
            'Jai Hind ki goonj sunaayi de',
            'Mere desh ki dharti sona ugle',
            'Veer jawano tum aage badho',
            'Tiranga yeh shaan hamari hai'
        ],
        imagery: [
            'himalaya ki chotion pe barf chamke',
            'ganga ki lehron mein desh ka garv hai',
            'tiranga lehraata hai aasmaan mein',
            'sarhad pe jawan khadey hain',
            'khet khalihanon mein sona ugta hai',
            'subah ki azan aur shaam ki aarti'
        ],
        endLines: [
            'Jai Hind, Jai Bharat',
            'mera desh meri jaan hai',
            'desh ke liye sab kuch qurbaan',
            'vatan ki mitti mein mil jaana hai',
            'yeh Hindustan hamara hai',
            'jab tak saans hai, desh pehle hai'
        ]
    }
};

// Structural templates for building lines
const lineTemplates = [
    (v) => `${pick(v.subjects)} ${pick(v.verbs)}`,
    (v) => `${pick(v.phrases)}`,
    (v) => `${pick(v.hooks)}`,
    (v) => `${pick(v.imagery)}`,
    (v) => `${pick(v.subjects)}, ${pick(v.phrases)}`,
    (v) => `${pick(v.imagery)}, ${pick(v.endLines)}`,
];

function pick(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
}

function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

function generateLine(vocab) {
    const template = lineTemplates[Math.floor(Math.random() * lineTemplates.length)];
    return capitalize(template(vocab));
}

function generateMukhda(vocab) {
    const hookLine = capitalize(pick(vocab.hooks));
    const line2 = capitalize(`${pick(vocab.phrases)}`);
    const line3 = capitalize(`${pick(vocab.subjects)} ${pick(vocab.verbs)}`);
    const line4 = hookLine; // repeat hook for chorus effect
    return { label: 'Mukhda (Chorus)', lines: [hookLine, line2, line3, line4] };
}

function generateAntara(vocab, number) {
    const lines = [];
    // First couplet
    lines.push(capitalize(`${pick(vocab.imagery)}`));
    lines.push(capitalize(`${pick(vocab.phrases)}`));
    // Second couplet
    lines.push(capitalize(`${pick(vocab.subjects)} ${pick(vocab.verbs)}`));
    lines.push(capitalize(`${pick(vocab.endLines)}`));
    return { label: `Antara ${number}`, lines };
}

function generateLyrics() {
    const mood = document.getElementById('mood').value;
    const structure = document.getElementById('structure').value;
    const vocab = vocabulary[mood];

    const sections = [];

    if (structure === 'mukhda') {
        sections.push(generateMukhda(vocab));
    } else if (structure === 'single') {
        sections.push(generateMukhda(vocab));
        sections.push(generateAntara(vocab, 1));
    } else {
        // full song
        sections.push(generateMukhda(vocab));
        sections.push(generateAntara(vocab, 1));
        sections.push({ label: 'Mukhda (Repeat)', lines: sections[0].lines });
        sections.push(generateAntara(vocab, 2));
        sections.push({ label: 'Mukhda (Final)', lines: sections[0].lines });
    }

    renderLyrics(sections);
}

function renderLyrics(sections) {
    const container = document.getElementById('lyrics-content');
    const output = document.getElementById('lyrics-output');
    container.innerHTML = '';

    sections.forEach((section, idx) => {
        if (idx > 0) {
            const spacer = document.createElement('div');
            spacer.className = 'line-break';
            container.appendChild(spacer);
        }

        const label = document.createElement('div');
        label.className = 'section-label';
        label.textContent = section.label;
        container.appendChild(label);

        section.lines.forEach(line => {
            const lineEl = document.createElement('div');
            lineEl.className = 'lyric-line';
            lineEl.textContent = line;
            container.appendChild(lineEl);
        });
    });

    output.classList.remove('hidden');
}

function copyLyrics() {
    const output = document.getElementById('lyrics-content');
    const sections = output.querySelectorAll('.section-label');
    let text = '';

    sections.forEach(section => {
        text += `[ ${section.textContent} ]\n`;
        let sibling = section.nextElementSibling;
        while (sibling && !sibling.classList.contains('section-label') && !sibling.classList.contains('line-break')) {
            text += sibling.textContent + '\n';
            sibling = sibling.nextElementSibling;
        }
        text += '\n';
    });

    navigator.clipboard.writeText(text.trim()).then(() => {
        const btn = document.querySelector('.action-btn');
        const original = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = original; }, 1500);
    });
}
