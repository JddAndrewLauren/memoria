# Answer-key spot check

Six rows from `benchmark/answer-key.yaml`, drawn with a fixed seed
(`random.Random(9)`; three per work, sampled from the resolved rows of that work
sorted by `link_id`), so the sample is reproducible and was not chosen after
seeing the answers.

## What is being checked, and what is not

**Not** "did Thoreau rewrite this journal passage into that book passage". That is
the 1906 editors' judgement, recorded in their own footnote, and the key takes it
on their authority — deciding it here would mean reading evidence against
manuscript prose for similarity, which is the operation the benchmark measures
(`docs/answer-key-protocol.md`, "What may not be done").

**Only this:** does the page the footnote cites hold the text the key names? The
scanned Manuscript Edition and the held Gutenberg text are two printings of one
book, so they should read the same, allowing for OCR damage.

The quickest way to check a row: take the **first few words** and the **last few
words** of the scanned page, and find them in the held span below it. They should
both be there, in that order. The span is wider than the page at both ends,
because a page starts and ends mid-paragraph and the key records whole paragraphs.

Verdict per row: **matches** / **does not match**.

---

## 1. `src-000305-p8/Week`

- Footnote: `[This poem appears in _Week_, p. 50 (Riv. 62), with some variations and without title.]`
- Key says: **Week / SUNDAY / paragraphs 24-29**
- Anchors: `src-000720-p24` … `src-000720-p29`
- Edition cross-check: Riverside p. 62, residual +0.89 pages

**Look for these, in the span below:**

- opens: `the forest beyond the plantations of the white man; but to-day I`
- closes: `blacksmith's shop, for centre, and a good deal of wood to cut`

<details>
<summary>Manuscript Edition page 50, as scanned (241 words)</summary>

```
the forest beyond the plantations of the white man; but to-day I like best
the echo amid these cliffs and woods. It is no 50 A WEEK feeble imitation,
but rather its original, or as if some rural Orpheus played over the strain
again to show how it should sound. Dong, sounds the brass in the east, As if
to a funeral feast, But I like that sound the best Out of the fluttering
west. The steeple ringeth a knell, But the fairies' silvery bell Is the
voice of that gentle folk, Or else the horizon that spoke. Its metal is not
of brass, But air, and water, and glass, And under a cloud it is swung, And
by the wind it is rung. When the steeple tolleth the noon, It soundeth not
so soon, Yet it rings a far earlier hour, And the sun has not reached its
tower. On the other hand, the road runs up to Carlisle, city of the woods,
which, if it is less civil, is the more natural. It does well hold the earth
together. It gets laughed at because it is a small town, I know, but
nevertheless it is a place where great men may be born any day, for fair
winds and foul blow right on over it without distinction. It has a meeting-
house and horse-sheds, a tavern and a blacksmith's shop, for centre, and a
good deal of wood to cut
```
</details>

### Held text, Week / SUNDAY / paragraphs 24-29

```
Here was a village not far off behind the woods, Billerica, settled not long
ago, and the children still bear the names of the first settlers in this
late "howling wilderness"; yet to all intents and purposes it is as old as
Fernay or as Mantua, an old gray town where men grow old and sleep already
under moss-grown monuments,—outgrow their usefulness. This is ancient
Billerica, (Villarica?) now in its dotage, named from the English
Billericay, and whose Indian name was Shawshine. I never heard that it was
young. See, is not nature here gone to decay, farms all run out, meeting-
house grown gray and racked with age? If you would know of its early youth,
ask those old gray rocks in the pasture. It has a bell that sounds sometimes
as far as Concord woods; I have heard that,—ay, hear it now. No wonder that
such a sound startled the dreaming Indian, and frightened his game, when the
first bells were swung on trees, and sounded through the forest beyond the
plantations of the white man. But to-day I like best the echo amid these
cliffs and woods. It is no feeble imitation, but rather its original, or as
if some rural Orpheus played over the strain again to show how it should
sound. Dong, sounds the brass in the east, As if to a funeral feast, But I
like that sound the best Out of the fluttering west. The steeple ringeth a
knell, But the fairies' silvery bell Is the voice of that gentle folk, Or
else the horizon that spoke. Its metal is not of brass, But air, and water,
and glass, And under a cloud it is swung, And by the wind it is rung. When
the steeple tolleth the noon, It soundeth not so soon, Yet it rings a far
earlier hour, And the sun has not reached its tower. On the other hand, the
road runs up to Carlisle, city of the woods, which, if it is less civil, is
the more natural. It does well hold the earth together. It gets laughed at
because it is a small town, I know, but nevertheless it is a place where
great men may be born any day, for fair winds and foul blow right on over it
without distinction. It has a meeting-house and horse-sheds, a tavern and a
blacksmith's shop, for centre, and a good deal of wood to cut and cord yet.
And
```

**Verdict:** matches

---

## 2. `src-000339-p2/Week`

- Footnote: `[_Week_, p. 291; Riv. 361.]`
- Key says: **Week / WEDNESDAY / paragraphs 103-105**
- Anchors: `src-000723-p103` … `src-000723-p105`
- Edition cross-check: Riverside p. 361, residual +0.97 pages

**Look for these, in the span below:**

- opens: `durable it is serene and equable. Even its famous pains begin only`
- closes: `blossomless nor fruit- less, is remembered with satisfaction and security. The stern`

<details>
<summary>Manuscript Edition page 291, as scanned (288 words)</summary>

```
durable it is serene and equable. Even its famous pains begin only with the
ebb of love, for few are indeed lovers, though all would fain be. It is one
proof of a man's fitness for Friendship that he is able to do without that
which is cheap and passionate. A true Friendship is as wise as it is tender.
The parties to it yield implicitly to the guidance of their love, and know
no other law nor kindness. It is not extravagant and insane, but what it
says is something established WEDNESDAY 291 henceforth, and will bear to be
stereotyped. It is a truer truth, it is better and fairer news, and no time
will ever shame it, or prove it false. This is a plant which thrives best in
a temperate zone, where summer and winter alternate with one another. The
Friend is a necessarius, and meets his Friend on homely ground ; not on
carpets and cushions, but on the ground and on rocks they will sit, obeying
the natural and primitive laws. They will meet without any outcry, and part
without loud sorrow. Their relation implies such qualities as the warrior
prizes ; for it takes a valor to open the hearts of men as well as the gates
of castles. It is not an idle sympathy and mutual consolation merely, but a
heroic sympathy of aspiration and endeavor. "When manhood shall be matched
so That fear can take no place, Then weary works make warriors Each other to
embrace." The Friendship which Wawatam testified for Henry the fur-trader,
as described in the latter's "Adventures," so almost bare and leafless, yet
not blossomless nor fruit- less, is remembered with satisfaction and
security. The stern
```
</details>

### Held text, Week / WEDNESDAY / paragraphs 103-105

```
The violence of love is as much to be dreaded as that of hate. When it is
durable it is serene and equable. Even its famous pains begin only with the
ebb of love, for few are indeed lovers, though all would fain be. It is one
proof of a man's fitness for Friendship that he is able to do without that
which is cheap and passionate. A true Friendship is as wise as it is tender.
The parties to it yield implicitly to the guidance of their love, and know
no other law nor kindness. It is not extravagant and insane, but what it
says is something established henceforth, and will bear to be stereotyped.
It is a truer truth, it is better and fairer news, and no time will ever
shame it, or prove it false. This is a plant which thrives best in a
temperate zone, where summer and winter alternate with one another. The
Friend is a _necessarius_, and meets his Friend on homely ground; not on
carpets and cushions, but on the ground and on rocks they will sit, obeying
the natural and primitive laws. They will meet without any outcry, and part
without loud sorrow. Their relation implies such qualities as the warrior
prizes; for it takes a valor to open the hearts of men as well as the gates
of castles. It is not an idle sympathy and mutual consolation merely, but a
heroic sympathy of aspiration and endeavor. "When manhood shall be matched
so That fear can take no place, Then weary _works_ make warriors Each other
to embrace." The Friendship which Wawatam testified for Henry the fur-
trader, as described in the latter's "Adventures," so almost bare and
leafless, yet not blossomless nor fruitless, is remembered with satisfaction
and security. The stern, imperturbable warrior, after fasting, solitude, and
mortification of body, comes to the white man's lodge, and affirms that he
is the white brother whom he saw in his dream, and adopts him henceforth. He
buries the hatchet as it regards his friend, and they hunt and feast and
make maple-sugar together. "Metals unite from fluxility; birds and beasts
from motives of convenience; fools from fear and stupidity; and just men at
sight." If Wawatam would taste the "white man's milk" with his tribe, or
take his bowl of human broth made of the trader's fellow-countrymen, he
first finds a place of safety for his Friend, whom he has rescued from a
similar fate. At length, after a long winter of undisturbed and happy
intercourse in the family of the chieftain in the wilderness, hunting and
fishing, they return in the spring to Michilimackinac to dispose of their
furs; and it becomes necessary for Wawatam to take leave of his Friend at
the Isle aux Outardes, when the latter, to avoid his enemies, proceeded to
the Sault de Sainte Marie, supposing that they were to be separated for a
short time only. "We now exchanged farewells," says Henry, "with an emotion
entirely reciprocal. I did not quit the lodge without the most grateful
sense of the many acts of goodness which I had experienced in it, nor
without the sincerest respect for the virtues which I had witnessed among
its members. All the family accompanied me to the beach; and the canoe had
no sooner put off than Wawatam commenced an address to the Kichi Manito,
beseeching him to take care of me, his brother, till we should next meet. We
had proceeded to too great a distance to allow of our hearing his voice,
before Wawatam had ceased to offer up his prayers." We never hear of him
again.
```

**Verdict:** matches

---

## 3. `src-000247-p14/Week`

- Footnote: `[_Week_, p. 236; Riv. 293.]`
- Key says: **Week / TUESDAY / paragraphs 89-91**
- Anchors: `src-000722-p89` … `src-000722-p91`
- Edition cross-check: Riverside p. 293, residual -0.59 pages

**Look for these, in the span below:**

- opens: `me, and their gentle and tremulous cooing. They sojourned with us during`
- closes: `our vice. Where is the skillful swordsman who can give clean woun`

<details>
<summary>Manuscript Edition page 236, as scanned (292 words)</summary>

```
me, and their gentle and tremulous cooing. They sojourned with us during the
noontide, greater travelers far than we. You may frequently discover a
single pair sitting upon the lower branches of the white pine in the depths
of the wood, at this hour of the day, so silent and solitary, and with such
a hermitlike appearance, as if they had never strayed beyond its skirts,
while the acorn 236 A WEEK which was gathered in the forests of Maine is
still undi- gested in their crops. We obtained one of these hand- some
birds, which lingered too long upon its perch, and plucked and broiled it
here with some other game, to be carried along for our supper; for, beside
the provisions which we carried with us, we depended mainly on the river and
forest for our supply. It is true, it did not seem to be putting this bird
to its right use to pluck off its feathers, and extract its entrails, and
broil its carcass on the coals; but we heroically persevered, nevertheless,
waiting for further information. The same regard for Nature which excited
our sympathy for her creatures nerved our hands to carry through what we had
begun. For we would be honorable to the party we deserted; we would fulfill
fate, and so at length, perhaps, detect the secret innocence of these
incessant tragedies which Heaven allows. "Too quick resolves do resolution
wrong. What, part so soon to be divorced so long ? Things to be done are
long to be debated; Heaven is not day'd, Repentance is not dated." We are
double-edged blades, and every time we whet our virtue the return stroke
straps our vice. Where is the skillful swordsman who can give clean woun
```
</details>

### Held text, Week / TUESDAY / paragraphs 89-91

```
During the heat of the day, we rested on a large island a mile above the
mouth of this river, pastured by a herd of cattle, with steep banks and
scattered elms and oaks, and a sufficient channel for canal-boats on each
side. When we made a fire to boil some rice for our dinner, the flames
spreading amid the dry grass, and the smoke curling silently upward and
casting grotesque shadows on the ground, seemed phenomena of the noon, and
we fancied that we progressed up the stream without effort, and as naturally
as the wind and tide went down, not outraging the calm days by unworthy
bustle or impatience. The woods on the neighboring shore were alive with
pigeons, which were moving south, looking for mast, but now, like ourselves,
spending their noon in the shade. We could hear the slight, wiry, winnowing
sound of their wings as they changed their roosts from time to time, and
their gentle and tremulous cooing. They sojourned with us during the
noontide, greater travellers far than we. You may frequently discover a
single pair sitting upon the lower branches of the white-pine in the depths
of the wood, at this hour of the day, so silent and solitary, and with such
a hermit-like appearance, as if they had never strayed beyond its skirts,
while the acorn which was gathered in the forests of Maine is still
undigested in their crops. We obtained one of these handsome birds, which
lingered too long upon its perch, and plucked and broiled it here with some
other game, to be carried along for our supper; for, beside the provisions
which we carried with us, we depended mainly on the river and forest for our
supply. It is true, it did not seem to be putting this bird to its right use
to pluck off its feathers, and extract its entrails, and broil its carcass
on the coals; but we heroically persevered, nevertheless, waiting for
further information. The same regard for Nature which excited our sympathy
for her creatures nerved our hands to carry through what we had begun. For
we would be honorable to the party we deserted; we would fulfil fate, and so
at length, perhaps, detect the secret innocence of these incessant tragedies
which Heaven allows. "Too quick resolves do resolution wrong, What, part so
soon to be divorced so long? Things to be done are long to be debated;
Heaven is not day'd, Repentance is not dated." We are double-edged blades,
and every time we whet our virtue the return stroke straps our vice. Where
is the skilful swordsman who can give clean wounds, and not rip up his work
with the other edge?
```

**Verdict:** matches

---

## 4. `src-000391-p6/Walden`

- Footnote: `[_Walden_, p. 232; Riv. 327.]`
- Key says: **Walden / Baker Farm + Higher Laws / paragraphs 17-1**
- Anchors: `src-000735-p17` … `src-000736-p1`
- Edition cross-check: Riverside p. 327, residual +0.45 pages

**Look for these, in the span below:**

- opens: `seats too. Poor John Field ! — I trust he does not`
- closes: `it is named, spiritual life, as do most men, and another t`

<details>
<summary>Manuscript Edition page 232, as scanned (242 words)</summary>

```
seats too. Poor John Field ! — I trust he does not read this, unless he will
improve by it, — thinking to live by some derivative old country mode in
this primitive new country, — to catch perch with shiners. It is good bait
sometimes, I allow. With his horizon all his own, yet he a poor man, born to
be poor, with his inherited Irish poverty or poor life, his Adam's
grandmother and boggy ways, not to rise in this world, he nor his posterity,
till their wading webbed bog-trotting feet get talaria to their heels. XI
HIGHER LAWS -A.S I came home through the woods with my string of fish,
trailing my pole, it being now quite dark, I caught a glimpse of a woodchuck
stealing across my path, and felt a strange thrill of savage delight, and
was strongly tempted to seize and devour him raw; not that I was hungry
then, except for that wildness which he represented. Once or twice, however,
while I lived at the pond, I found myself ranging the woods, like a half-
starved hound, with a strange abandonment, seek- ing some kind of venison
which I might devour, and no morsel could have been too savage for me. The
wild- est scenes had become unaccountably familiar. I found in myself, and
still find, an instinct toward a higher, or, as it is named, spiritual life,
as do most men, and another t
```
</details>

### Held text, Walden / Baker Farm + Higher Laws / paragraphs 17-1

```
Before I had reached the pond some fresh impulse had brought out John Field,
with altered mind, letting go "bogging" ere this sunset. But he, poor man,
disturbed only a couple of fins while I was catching a fair string, and he
said it was his luck; but when we changed seats in the boat luck changed
seats too. Poor John Field!—I trust he does not read this, unless he will
improve by it,—thinking to live by some derivative old country mode in this
primitive new country,—to catch perch with shiners. It is good bait
sometimes, I allow. With his horizon all his own, yet he a poor man, born to
be poor, with his inherited Irish poverty or poor life, his Adam's
grandmother and boggy ways, not to rise in this world, he nor his posterity,
till their wading webbed bog-trotting feet get _talaria_ to their heels. As
I came home through the woods with my string of fish, trailing my pole, it
being now quite dark, I caught a glimpse of a woodchuck stealing across my
path, and felt a strange thrill of savage delight, and was strongly tempted
to seize and devour him raw; not that I was hungry then, except for that
wildness which he represented. Once or twice, however, while I lived at the
pond, I found myself ranging the woods, like a half-starved hound, with a
strange abandonment, seeking some kind of venison which I might devour, and
no morsel could have been too savage for me. The wildest scenes had become
unaccountably familiar. I found in myself, and still find, an instinct
toward a higher, or, as it is named, spiritual life, as do most men, and
another toward a primitive rank and savage one, and I reverence them both. I
love the wild not less than the good. The wildness and adventure that are in
fishing still recommended it to me. I like sometimes to take rank hold on
life and spend my day more as the animals do. Perhaps I have owed to this
employment and to hunting, when quite young, my closest acquaintance with
Nature. They early introduce us to and detain us in scenery with which
otherwise, at that age, we should have little acquaintance. Fishermen,
hunters, woodchoppers, and others, spending their lives in the fields and
woods, in a peculiar sense a part of Nature themselves, are often in a more
favorable mood for observing her, in the intervals of their pursuits, than
philosophers or poets even, who approach her with expectation. She is not
afraid to exhibit herself to them. The traveller on the prairie is naturally
a hunter, on the head waters of the Missouri and Columbia a trapper, and at
the Falls of St. Mary a fisherman. He who is only a traveller learns things
at second-hand and by the halves, and is poor authority. We are most
interested when science reports what those men already know practically or
instinctively, for that alone is a true _humanity_, or account of human
experience.
```

**Verdict:** matches

---

## 5. `src-000388-p8/Walden`

- Footnote: `[_Walden_, pp. 159, 160; Riv. 224, 225.]`
- Key says: **Walden / Visitors / paragraphs 7-11**
- Anchors: `src-000731-p7` … `src-000731-p11`
- Edition cross-check: Riverside p. 224, residual -0.18 pages

**Look for these, in the span below:**

- opens: `o'clock the next day Massasoit "brought two fishes that he had shot,"`
- closes: `most part, so far as my needs were concerned, only the fin`

<details>
<summary>Manuscript Edition page 159, as scanned (310 words)</summary>

```
o'clock the next day Massasoit "brought two fishes that he had shot," about
thrice as big as a bream; "these being boiled, there were at least forty
looked for a share in them. The most ate of them. This meal only we had in
two nights and a day; and had not one of us bought a partridge, we had taken
our journey fasting." Fearing that they VISITORS 159 would be light-headed
for want of food and also sleep, owing to "the savages' barbarous singing,
(for they used to sing themselves asleep,) " and that they might get home
while they had strength to travel, they departed. As for lodging, it is true
they were but poorly entertained, though what they found an inconvenience
was no doubt intended for an honor; but as far as eating was con- cerned, I
do not see how the Indians could have done better. They had nothing to eat
themselves, and they were wiser than to think that apologies could supply
the place of food to their guests; so they drew their belts tighter and said
nothing about it. Another time when Winslow visited them, it being a season
of plenty with them, there was no deficiency in this respect. As for men,
they will hardly fail one anywhere. I had more visitors while I lived in the
woods than at any other period of my life ; I mean that I had some. I met
several there under more favorable circumstances than I could anywhere else.
But fewer came to see me on trivial busi- ness. In this respect, my company
was winnowed by my mere distance from town. I had withdrawn so far within
the great ocean of solitude, into which the rivers of so- ciety empty, that
for the most part, so far as my needs were concerned, only the fin
```
</details>

### Held text, Walden / Visitors / paragraphs 7-11

```
When Winslow, afterward governor of the Plymouth Colony, went with a
companion on a visit of ceremony to Massasoit on foot through the woods, and
arrived tired and hungry at his lodge, they were well received by the king,
but nothing was said about eating that day. When the night arrived, to quote
their own words,—"He laid us on the bed with himself and his wife, they at
the one end and we at the other, it being only planks laid a foot from the
ground, and a thin mat upon them. Two more of his chief men, for want of
room, pressed by and upon us; so that we were worse weary of our lodging
than of our journey." At one o'clock the next day Massasoit "brought two
fishes that he had shot," about thrice as big as a bream; "these being
boiled, there were at least forty looked for a share in them. The most ate
of them. This meal only we had in two nights and a day; and had not one of
us bought a partridge, we had taken our journey fasting." Fearing that they
would be light-headed for want of food and also sleep, owing to "the
savages' barbarous singing, (for they used to sing themselves asleep,)" and
that they might get home while they had strength to travel, they departed.
As for lodging, it is true they were but poorly entertained, though what
they found an inconvenience was no doubt intended for an honor; but as far
as eating was concerned, I do not see how the Indians could have done
better. They had nothing to eat themselves, and they were wiser than to
think that apologies could supply the place of food to their guests; so they
drew their belts tighter and said nothing about it. Another time when
Winslow visited them, it being a season of plenty with them, there was no
deficiency in this respect. As for men, they will hardly fail one any where.
I had more visitors while I lived in the woods than at any other period in
my life; I mean that I had some. I met several there under more favorable
circumstances than I could any where else. But fewer came to see me on
trivial business. In this respect, my company was winnowed by my mere
distance from town. I had withdrawn so far within the great ocean of
solitude, into which the rivers of society empty, that for the most part, so
far as my needs were concerned, only the finest sediment was deposited
around me. Beside, there were wafted to me evidences of unexplored and
uncultivated continents on the other side. Who should come to my lodge this
morning but a true Homeric or Paphlagonian man,—he had so suitable and
poetic a name that I am sorry I cannot print it here,—a Canadian, a
woodchopper and post-maker, who can hole fifty posts in a day, who made his
last supper on a woodchuck which his dog caught. He, too, has heard of
Homer, and, "if it were not for books," would "not know what to do rainy
days," though perhaps he has not read one wholly through for many rainy
seasons. Some priest who could pronounce the Greek itself taught him to read
his verse in the testament in his native parish far away; and now I must
translate to him, while he holds the book, Achilles' reproof to Patroclus
for his sad countenance.—"Why are you in tears, Patroclus, like a young
girl?"— "Or have you alone heard some news from Phthia? They say that
Menœtius lives yet, son of Actor, And Peleus lives, son of Æacus, among the
Myrmidons, Either of whom having died, we should greatly grieve." He says,
"That's good." He has a great bundle of white-oak bark under his arm for a
sick man, gathered this Sunday morning. "I suppose there's no harm in going
after such a thing to-day," says he. To him Homer was a great writer, though
what his writing was about he did not know. A more simple and natural man it
would be hard to find. Vice and disease, which cast such a sombre moral hue
over the world, seemed to have hardly any existence for him. He was about
twenty-eight years old, and had left Canada and his father's house a dozen
years before to work in the States, and earn money to buy a farm with at
last, perhaps in his native country. He was cast in the coarsest mould; a
stout but sluggish body, yet gracefully carried, with a thick sunburnt neck,
dark bushy hair, and dull sleepy blue eyes, which were occasionally lit up
with expression. He wore a flat gray cloth cap, a dingy wool-colored
greatcoat, and cowhide boots. He was a great consumer of meat, usually
carrying his dinner to his work a couple of miles past my house,—for he
chopped all summer,—in a tin pail; cold meats, often cold woodchucks, and
coffee in a stone bottle which dangled by a string from his belt; and
sometimes he offered me a drink. He came along early, crossing my bean-
field, though without anxiety or haste to get to his work, such as Yankees
exhibit. He wasn't a-going to hurt himself. He didn't care if he only earned
his board. Frequently he would leave his dinner in the bushes, when his dog
had caught a woodchuck by the way, and go back a mile and a half to dress it
and leave it in the cellar of the house where he boarded, after deliberating
first for half an hour whether he could not sink it in the pond safely till
nightfall,—loving to dwell long upon these themes. He would say, as he went
by in the morning, "How thick the pigeons are! If working every day were not
my trade, I could get all the meat I should want by hunting,—pigeons,
woodchucks, rabbits, partridges,—by gosh! I could get all I should want for
a week in one day."
```

**Verdict:** matches

---

## 6. `src-000390-p4/Walden`

- Footnote: `[_Walden_, p. 181; Riv. 255.]`
- Key says: **Walden / The Bean-Field / paragraphs 16-17**
- Anchors: `src-000732-p16` … `src-000732-p17`
- Edition cross-check: Riverside p. 255, residual -0.29 pages

**Look for these, in the span below:**

- opens: `common small white bush bean about the first of June, in rows`
- closes: `astonishment, making the holes with a hoe for the seven- tieth t`

<details>
<summary>Manuscript Edition page 181, as scanned (321 words)</summary>

```
common small white bush bean about the first of June, in rows three feet by
eighteen inches apart, be- ing careful to select fresh round and unmixed
seed. First look out for worms, and supply vacancies by planting anew. Then
look out for woodchucks, if it is an exposed place, for they will nibble off
the earliest tender leaves almost clean as they go; and again, when the
young tendrils make their appearance, they have notice of it, THE BEAN-FIELD
181 and will shear them off with both buds and young pods, sitting erect
like a squirrel. But above all harvest as early as possible, if you would
escape frosts and have a fair and salable crop; you may save much loss by
this means. This further experience also I gained. I said to my- self, I
will not plant beans and corn with so much in- dustry another summer, but
such seeds, if the seed is not lost, as sincerity, truth, simplicity, faith,
innocence, and the like, and see if they will not grow in this soil, even
with less toil and manurance, and sustain me, for surely it has not been
exhausted for these crops. Alas! I said this to myself; but now another
summer is gone, and another, and another, and I am obliged to say to you,
Reader, that the seeds which I planted, if indeed they were the seeds of
those virtues, were wormeaten or had lost their vitality, and so did not
come up. Commonly men will only be brave as their fathers were brave, or
timid. This generation is very sure to plant corn and beans each new year
precisely as the Indians did cen- turies ago and taught the first settlers
to do, as if there were a fate in it. I saw an old man the other day, to my
astonishment, making the holes with a hoe for the seven- tieth t
```
</details>

### Held text, Walden / The Bean-Field / paragraphs 16-17

```
This is the result of my experience in raising beans. Plant the common small
white bush bean about the first of June, in rows three feet by eighteen
inches apart, being careful to select fresh round and unmixed seed. First
look out for worms, and supply vacancies by planting anew. Then look out for
woodchucks, if it is an exposed place, for they will nibble off the earliest
tender leaves almost clean as they go; and again, when the young tendrils
make their appearance, they have notice of it, and will shear them off with
both buds and young pods, sitting erect like a squirrel. But above all
harvest as early as possible, if you would escape frosts and have a fair and
salable crop; you may save much loss by this means. This further experience
also I gained. I said to myself, I will not plant beans and corn with so
much industry another summer, but such seeds, if the seed is not lost, as
sincerity, truth, simplicity, faith, innocence, and the like, and see if
they will not grow in this soil, even with less toil and manurance, and
sustain me, for surely it has not been exhausted for these crops. Alas! I
said this to myself; but now another summer is gone, and another, and
another, and I am obliged to say to you, Reader, that the seeds which I
planted, if indeed they _were_ the seeds of those virtues, were wormeaten or
had lost their vitality, and so did not come up. Commonly men will only be
brave as their fathers were brave, or timid. This generation is very sure to
plant corn and beans each new year precisely as the Indians did centuries
ago and taught the first settlers to do, as if there were a fate in it. I
saw an old man the other day, to my astonishment, making the holes with a
hoe for the seventieth time at least, and not for himself to lie down in!
But why should not the New Englander try new adventures, and not lay so much
stress on his grain, his potato and grass crop, and his orchards,—raise
other crops than these? Why concern ourselves so much about our beans for
seed, and not be concerned at all about a new generation of men? We should
really be fed and cheered if when we met a man we were sure to see that some
of the qualities which I have named, which we all prize more than those
other productions, but which are for the most part broadcast and floating in
the air, had taken root and grown in him. Here comes such a subtile and
ineffable quality, for instance, as truth or justice, though the slightest
amount or new variety of it, along the road. Our ambassadors should be
instructed to send home such seeds as these, and Congress help to distribute
them over all the land. We should never stand upon ceremony with sincerity.
We should never cheat and insult and banish one another by our meanness, if
there were present the kernel of worth and friendliness. We should not meet
thus in haste. Most men I do not meet at all, for they seem not to have
time; they are busy about their beans. We would not deal with a man thus
plodding ever, leaning on a hoe or a spade as a staff between his work, not
as a mushroom, but partially risen out of the earth, something more than
erect, like swallows alighted and walking on the ground:—
```

**Verdict:** matches

---
