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

## 1. `src-000294-p3/Week`

- Footnote: `[_Week_, pp. 318, 319; Riv. 395. Tree sparrow = chipping sparrow? The "hair-bird" of _Week_, p. 317 (Riv. 393), is called tree sparrow in the commonplace-book referred to on p. 438.]`
- Key says: **Week / THURSDAY / paragraphs 3-5**
- Anchors: `src-000724-p3` … `src-000724-p5`
- Edition cross-check: Riverside p. 395, residual -1.25 pages

**Look for these, in the span below:**

- opens: `and in the pastures, and instead of any bow in the heavens,`
- closes: `our path with as much pleasure and buoyancy as in brightest sunsh`

<details>
<summary>Manuscript Edition page 318, as scanned (302 words)</summary>

```
and in the pastures, and instead of any bow in the heavens, there was the
trill of the hair- bird all the morning. The cheery faith of this little
bird atoned for the silence of the whole woodland choir beside. When we
first stepped abroad, a flock of sheep, led by their rams, came rushing down
a ravine in our rear, with heedless haste and unreserved frisk- ing, as if
unobserved by man, from some higher pas- ture where they had spent the
night, to taste the herbage by the riverside ; but when their leaders caught
sight 318 A WEEK of our white tent through the mist, struck with sudden
astonishment, with their fore feet braced, they sustained the rushing
torrent in their rear, and the whole flock stood stock-still, endeavoring to
solve the mystery in their sheepish brains. At length, concluding that it
boded no mischief to them, they spread themselves out quietly over the
field. We learned afterward that we had pitched our tent on the very spot
which a few sum- mers before had been occupied by a party of Penob- scots.
We could see rising before us through the mist a dark conical eminence
called Hooksett Pinnacle, a landmark to boatmen, and also Uncannunuc
Mountain, broad off on the west side of the river. This was the limit of our
voyage, for a few hours more in the rain would have taken us to the last of
the locks, and our boat was too heavy to be dragged around the long and
numerous rapids which would occur. On foot, however, we continued up along
the bank, feeling our way with a stick through the showery and foggy day,
and climbing over the slippery logs in our path with as much pleasure and
buoyancy as in brightest sunsh
```
</details>

### Held text, Week / THURSDAY / paragraphs 3-5

```
When we awoke this morning, we heard the faint, deliberate, and ominous
sound of rain-drops on our cotton roof. The rain had pattered all night, and
now the whole country wept, the drops falling in the river, and on the
alders, and in the pastures, and instead of any bow in the heavens, there
was the trill of the hair-bird all the morning. The cheery faith of this
little bird atoned for the silence of the whole woodland choir beside. When
we first stepped abroad, a flock of sheep, led by their rams, came rushing
down a ravine in our rear, with heedless haste and unreserved frisking, as
if unobserved by man, from some higher pasture where they had spent the
night, to taste the herbage by the river-side; but when their leaders caught
sight of our white tent through the mist, struck with sudden astonishment,
with their fore-feet braced, they sustained the rushing torrent in their
rear, and the whole flock stood stock-still, endeavoring to solve the
mystery in their sheepish brains. At length, concluding that it boded no
mischief to them, they spread themselves out quietly over the field. We
learned afterward that we had pitched our tent on the very spot which a few
summers before had been occupied by a party of Penobscots. We could see
rising before us through the mist a dark conical eminence called Hooksett
Pinnacle, a landmark to boatmen, and also Uncannunuc Mountain, broad off on
the west side of the river. This was the limit of our voyage, for a few
hours more in the rain would have taken us to the last of the locks, and our
boat was too heavy to be dragged around the long and numerous rapids which
would occur. On foot, however, we continued up along the bank, feeling our
way with a stick through the showery and foggy day, and climbing over the
slippery logs in our path with as much pleasure and buoyancy as in brightest
sunshine; scenting the fragrance of the pines and the wet clay under our
feet, and cheered by the tones of invisible waterfalls; with visions of
toadstools, and wandering frogs, and festoons of moss hanging from the
spruce-trees, and thrushes flitting silent under the leaves; our road still
holding together through that wettest of weather, like faith, while we
confidently followed its lead. We managed to keep our thoughts dry, however,
and only our clothes were wet. It was altogether a cloudy and drizzling day,
with occasional brightenings in the mist, when the trill of the tree-sparrow
seemed to be ushering in sunny hours. "Nothing that naturally happens to man
can _hurt_ him, earthquakes and thunder-storms not excepted," said a man of
genius, who at this time lived a few miles farther on our road. When
compelled by a shower to take shelter under a tree, we may improve that
opportunity for a more minute inspection of some of Nature's works. I have
stood under a tree in the woods half a day at a time, during a heavy rain in
the summer, and yet employed myself happily and profitably there prying with
microscopic eye into the crevices of the bark or the leaves or the fungi at
my feet. "Riches are the attendants of the miser; and the heavens rain
plenteously upon the mountains." I can fancy that it would be a luxury to
stand up to one's chin in some retired swamp a whole summer day, scenting
the wild honeysuckle and bilberry blows, and lulled by the minstrelsy of
gnats and mosquitoes! A day passed in the society of those Greek sages, such
as described in the Banquet of Xenophon, would not be comparable with the
dry wit of decayed cranberry vines, and the fresh Attic salt of the moss-
beds. Say twelve hours of genial and familiar converse with the leopard
frog; the sun to rise behind alder and dogwood, and climb buoyantly to his
meridian of two hands' breadth, and finally sink to rest behind some bold
western hummock. To hear the evening chant of the mosquito from a thousand
green chapels, and the bittern begin to boom from some concealed fort like a
sunset gun!—Surely one may as profitably be soaked in the juices of a swamp
for one day as pick his way dry-shod over sand. Cold and damp,—are they not
as rich experience as warmth and dryness?
```

**Verdict:** 

---

## 2. `src-000329-p7/Week`

- Footnote: `[_Week_, p. 358; Riv. 443.]`
- Key says: **Week / FRIDAY / paragraphs 6-9**
- Anchors: `src-000725-p6` … `src-000725-p9`
- Edition cross-check: Riverside p. 443, residual +0.43 pages

**Look for these, in the span below:**

- opens: `and then went quietly in and shut the door, retreating inward to`
- closes: `the fall of the year. The low of cattle in the streets`

<details>
<summary>Manuscript Edition page 358, as scanned (310 words)</summary>

```
and then went quietly in and shut the door, retreating inward to the haunts
of sum- mer. "And now the cold autumnal dews are seen To cobweb eVry green;
And by the low-shorn rowens doth appear The fast<leclining year." We heard
the sigh of the first autumnal wind, and even the water had acquired a
grayer hue. The su- mach, grape, and maple were already changed, and the
milkweed had turned to a deep, rich yellow. In all woods the leaves were
fast ripening for their fall ; for their full veins and lively gloss mark
the ripe leaf and not the sered one of the poets ; and we knew that the 358
A WEEK maples, stripped of their leaves among the earliest, would soon stand
like a wreath of smoke along the edge of the meadow. Already the cattle were
heard to low wildly in the pastures and along the highways, restlessly
running to and fro, as if in apprehension of the with- ering of the grass
and of the approach of winter. Our thoughts, too, began to rustle. As I pass
along the streets of our village of Concord on the day of our annual Cattle-
Show, when it usually happens that the leaves of the elms and buttonwoods
begin first to strew the ground under the breath of the October wind, the
lively spirits in their sap seem to mount as high as any plow-boy's let
loose that day ; and they lead my thoughts away to the rustling woods, where
the trees are preparing for their winter campaign. This autumnal festival,
when men are gathered in crowds in the streets as regularly and by as
natural a law as the leaves cluster and rustle by the wayside, is naturally
associated in my mind with the fall of the year. The low of cattle in the
streets
```
</details>

### Held text, Week / FRIDAY / paragraphs 6-9

```
We found our boat in the dawn just as we had left it, and as if waiting for
us, there on the shore, in autumn, all cool and dripping with dew, and our
tracks still fresh in the wet sand around it, the fairies all gone or
concealed. Before five o'clock we pushed it into the fog, and, leaping in,
at one shove were out of sight of the shores, and began to sweep downward
with the rushing river, keeping a sharp lookout for rocks. We could see only
the yellow gurgling water, and a solid bank of fog on every side, forming a
small yard around us. We soon passed the mouth of the Souhegan, and the
village of Merrimack, and as the mist gradually rolled away, and we were
relieved from the trouble of watching for rocks, we saw by the flitting
clouds, by the first russet tinge on the hills, by the rushing river, the
cottages on shore, and the shore itself, so coolly fresh and shining with
dew, and later in the day, by the hue of the grape-vine, the goldfinch on
the willow, the flickers flying in flocks, and when we passed near enough to
the shore, as we fancied, by the faces of men, that the Fall had commenced.
The cottages looked more snug and comfortable, and their inhabitants were
seen only for a moment, and then went quietly in and shut the door,
retreating inward to the haunts of summer. "And now the cold autumnal dews
are seen To cobweb ev'ry green; And by the low-shorn rowens doth appear The
fast-declining year." We heard the sigh of the first autumnal wind, and even
the water had acquired a grayer hue. The sumach, grape, and maple were
already changed, and the milkweed had turned to a deep rich yellow. In all
woods the leaves were fast ripening for their fall; for their full veins and
lively gloss mark the ripe leaf, and not the sered one of the poets; and we
knew that the maples, stripped of their leaves among the earliest, would
soon stand like a wreath of smoke along the edge of the meadow. Already the
cattle were heard to low wildly in the pastures and along the highways,
restlessly running to and fro, as if in apprehension of the withering of the
grass and of the approach of winter. Our thoughts, too, began to rustle. As
I pass along the streets of our village of Concord on the day of our annual
Cattle-Show, when it usually happens that the leaves of the elms and
buttonwoods begin first to strew the ground under the breath of the October
wind, the lively spirits in their sap seem to mount as high as any plough-
boy's let loose that day; and they lead my thoughts away to the rustling
woods, where the trees are preparing for their winter campaign. This
autumnal festival, when men are gathered in crowds in the streets as
regularly and by as natural a law as the leaves cluster and rustle by the
wayside, is naturally associated in my mind with the fall of the year. The
low of cattle in the streets sounds like a hoarse symphony or running bass
to the rustling of the leaves. The wind goes hurrying down the country,
gleaning every loose straw that is left in the fields, while every farmer
lad too appears to scud before it,—having donned his best pea-jacket and
pepper-and-salt waistcoat, his unbent trousers, outstanding rigging of duck
or kerseymere or corduroy, and his furry hat withal,—to country fairs and
cattle-shows, to that Rome among the villages where the treasures of the
year are gathered. All the land over they go leaping the fences with their
tough, idle palms, which have never learned to hang by their sides, amid the
low of calves and the bleating of sheep,—Amos, Abner, Elnathan, Elbridge,—
```

**Verdict:** 

---

## 3. `src-000232-p4/Week-2`

- Footnote: `[_Week_, p. 229; Riv. 285. See also p. 124 of this volume.]`
- Key says: **Week / TUESDAY / paragraphs 67-72**
- Anchors: `src-000722-p67` … `src-000722-p72`
- Edition cross-check: Riverside p. 285, residual -0.54 pages

**Look for these, in the span below:**

- opens: `hether on rafts of logs or fagots, or sheepskins blown up. And`
- closes: `itself to us by its very antiquity and apparent solidity and nec`

<details>
<summary>Manuscript Edition page 229, as scanned (244 words)</summary>

```
hether on rafts of logs or fagots, or sheepskins blown up. And where could
they better afford to tarry meanwhile than on the banks of a river? As we
glided past at a distance, these outdoor work- men appeared to have added
some dignity to their labor by its very publicness. It was a part of the
industry of nature, like the work of hornets and mud wasps. 1 Ovid, Met. I.
133. TUESDAY 229 The waves slowly beat, Just to keep the noon sweet, And no
sound is floated o'er, Save the mallet on shore, Which echoing on high Seems
a-calking the sky. The haze, the sun's dust of travel, had a Lethean influ-
ence on the land and its inhabitants, and all creatures resigned themselves
to float upon the inappreciable tides of nature. Woof of the sun, ethereal
gauze, Woven of Nature's richest stuffs, Visible heat, air-water, and dry
sea, Last conquest of the eye ; Toil of the day displayed, sun-dust, Aerial
surf upon the shores of earth, Ethereal estuary, frith of light, Breakers of
air, billows of heat, Fine summer spray on inland seas ; Bird of the sun,
transparent-winged Owlet of noon, soft-pinioned, From heath or stubble
rising without song ; Establish thy serenity o'er the fields. The routine
which is in the sunshine and the finest days, as that which has conquered
and prevailed, com- mends itself to us by its very antiquity and apparent
solidity and nec
```
</details>

### Held text, Week / TUESDAY / paragraphs 67-72

```
Some carpenters were at work here mending a scow on the green and sloping
bank. The strokes of their mallets echoed from shore to shore, and up and
down the river, and their tools gleamed in the sun a quarter of a mile from
us, and we realized that boat-building was as ancient and honorable an art
as agriculture, and that there might be a naval as well as a pastoral life.
The whole history of commerce was made manifest in that scow turned bottom
upward on the shore. Thus did men begin to go down upon the sea in ships;
_quæque diu steterant in montibus altis, Fluctibus ignotis insultavêre
carinæ;_ "and keels which had long stood on high mountains careered
insultingly (_insultavêre_) over unknown waves." (Ovid, Met. I. 133.) We
thought that it would be well for the traveller to build his boat on the
bank of a stream, instead of finding a ferry or a bridge. In the Adventures
of Henry the fur-trader, it is pleasant to read that when with his Indians
he reached the shore of Ontario, they consumed two days in making two canoes
of the bark of the elm-tree, in which to transport themselves to Fort
Niagara. It is a worthy incident in a journey, a delay as good as much rapid
travelling. A good share of our interest in Xenophon's story of his retreat
is in the manœuvres to get the army safely over the rivers, whether on rafts
of logs or fagots, or sheep-skins blown up. And where could they better
afford to tarry meanwhile than on the banks of a river? As we glided past at
a distance, these out-door workmen appeared to have added some dignity to
their labor by its very publicness. It was a part of the industry of nature,
like the work of hornets and mud-wasps. The waves slowly beat, Just to keep
the noon sweet, And no sound is floated o'er, Save the mallet on shore,
Which echoing on high Seems a-calking the sky. The haze, the sun's dust of
travel, had a Lethean influence on the land and its inhabitants, and all
creatures resigned themselves to float upon the inappreciable tides of
nature. Woof of the sun, ethereal gauze, Woven of Nature's richest stuffs,
Visible heat, air-water, and dry sea, Last conquest of the eye; Toil of the
day displayed sun-dust, Aerial surf upon the shores of earth. Ethereal
estuary, frith of light, Breakers of air, billows of heat Fine summer spray
on inland seas; Bird of the sun, transparent-winged Owlet of noon, soft-
pinioned, From heath or stubble rising without song; Establish thy serenity
o'er the fields The routine which is in the sunshine and the finest days, as
that which has conquered and prevailed, commends itself to us by its very
antiquity and apparent solidity and necessity. Our weakness needs it, and
our strength uses it. We cannot draw on our boots without bracing ourselves
against it. If there were but one erect and solid standing tree in the
woods, all creatures would go to rub against it and make sure of their
footing. During the many hours which we spend in this waking sleep, the hand
stands still on the face of the clock, and we grow like corn in the night.
Men are as busy as the brooks or bees, and postpone everything to their
business; as carpenters discuss politics between the strokes of the hammer
while they are shingling a roof.
```

**Verdict:** 

---

## 4. `src-000391-p25/Walden-2`

- Footnote: `[_Walden_, p. 36; Riv. 55.]`
- Key says: **Walden / Economy / paragraphs 53-54**
- Anchors: `src-000726-p53` … `src-000726-p54`
- Edition cross-check: Riverside p. 55, residual -0.58 pages

**Look for these, in the span below:**

- opens: `am sur- prised to learn that they cannot at once name a`
- closes: `leg into it. This is the reason he is poor; and for`

<details>
<summary>Manuscript Edition page 36, as scanned (308 words)</summary>

```
am sur- prised to learn that they cannot at once name a dozen in 36 WALDEN
the town who own their farms free and clear. If you would know the history
of these homesteads, inquire at the bank where they are mortgaged. The man
who has actually paid for his farm with labor on it is so rare that every
neighbor can point to him. I doubt if there are three such men in Concord.
What has been said of the merchants, that a very large majority, even
ninety-seven in a hundred, are sure to fail, is equally true of the farmers.
With regard to the merchants, however, one of them says pertinently that a
great part of their fail- ures are not genuine pecuniary failures, but-
merely failures to fulfil their engagements, because it is incon- venient;
that is, it is the moral character that breaks down. But this puts an
infinitely worse face on the mat- ter, and suggests, beside, that probably
not even the other three succeed in saving their souls, but are per- chance
bankrupt in a worse sense than they who fail honestly. Bankruptcy and
repudiation are the spring- boards from which much of our civilization
vaults and turns its somersets, but the savage stands on the un- elastic
plank of famine. Yet the Middlesex Cattle Show goes off here with eclat
annually, as if all the joints of the agricultural machine were suent. The
farmer is endeavoring to solve the problem of a livelihood by a formula more
complicated than the problem itself. To get his shoestrings he speculates in
herds of cattle. With consummate skill he has set his trap with a hair
springe to catch comfort and inde- pendence, and then, as he turned away,
got his own leg into it. This is the reason he is poor; and for
```
</details>

### Held text, Walden / Economy / paragraphs 53-54

```
When I consider my neighbors, the farmers of Concord, who are at least as
well off as the other classes, I find that for the most part they have been
toiling twenty, thirty, or forty years, that they may become the real owners
of their farms, which commonly they have inherited with encumbrances, or
else bought with hired money,—and we may regard one third of that toil as
the cost of their houses,—but commonly they have not paid for them yet. It
is true, the encumbrances sometimes outweigh the value of the farm, so that
the farm itself becomes one great encumbrance, and still a man is found to
inherit it, being well acquainted with it, as he says. On applying to the
assessors, I am surprised to learn that they cannot at once name a dozen in
the town who own their farms free and clear. If you would know the history
of these homesteads, inquire at the bank where they are mortgaged. The man
who has actually paid for his farm with labor on it is so rare that every
neighbor can point to him. I doubt if there are three such men in Concord.
What has been said of the merchants, that a very large majority, even
ninety-seven in a hundred, are sure to fail, is equally true of the farmers.
With regard to the merchants, however, one of them says pertinently that a
great part of their failures are not genuine pecuniary failures, but merely
failures to fulfil their engagements, because it is inconvenient; that is,
it is the moral character that breaks down. But this puts an infinitely
worse face on the matter, and suggests, beside, that probably not even the
other three succeed in saving their souls, but are perchance bankrupt in a
worse sense than they who fail honestly. Bankruptcy and repudiation are the
springboards from which much of our civilization vaults and turns its
somersets, but the savage stands on the unelastic plank of famine. Yet the
Middlesex Cattle Show goes off here with _éclat_ annually, as if all the
joints of the agricultural machine were suent. The farmer is endeavoring to
solve the problem of a livelihood by a formula more complicated than the
problem itself. To get his shoestrings he speculates in herds of cattle.
With consummate skill he has set his trap with a hair spring to catch
comfort and independence, and then, as he turned away, got his own leg into
it. This is the reason he is poor; and for a similar reason we are all poor
in respect to a thousand savage comforts, though surrounded by luxuries. As
Chapman sings,—
```

**Verdict:** 

---

## 5. `src-000388-p25/Walden`

- Footnote: `[_Walden_, p. 114; Riv. 162.]`
- Key says: **Walden / Reading / paragraphs 4-5**
- Anchors: `src-000728-p4` … `src-000728-p5`
- Edition cross-check: Riverside p. 162, residual +0.04 pages

**Look for these, in the span below:**

- opens: `r him ; but the writer, whose more equable life is his`
- closes: `and is admitted to the circles of wealth and fashion, he t`

<details>
<summary>Manuscript Edition page 114, as scanned (307 words)</summary>

```
r him ; but the writer, whose more equable life is his occasion, and who
would be distracted by the event and the crowd which inspire the orator,
speaks to the intellect and heart of mankind, to all in any age who can
understand him. 114 WALDEN No wonder that Alexander carried the Iliad with
him on his expeditions in a precious casket. A written word is the choicest
of relics. It is something at once more intimate with us and more universal
than any other work of art. It is the work of art nearest to life itself. It
may be translated into every language, and not only be read but actually
breathed from all human lips ; — not be represented on canvas or in marble
only, but be carved out of the breath of life itself. The symbol of an
ancient man's thought becomes a modern man's speech. Two thousand summers
have imparted to the monu- ments of Grecian literature, as to her marbles,
only a maturer golden and autumnal tint, for they have car- ried their own
serene and celestial atmosphere into all lands to protect them against the
corrosion of time. Books are the treasured wealth of the world and the fit
inheritance of generations and nations. Books, the old- est and the best,
stand naturally and rightfully on the shelves of every cottage. They have no
cause of their own to plead, but while they enlighten and sustain the reader
his common sense will not refuse them. Their authors are a natural and
irresistible aristocracy in every society, and, more than kings or emperors,
exert an influence on mankind. When the illiterate and per- haps scornful
trader has earned by enterprise and in- dustry his coveted leisure and
independence, and is admitted to the circles of wealth and fashion, he t
```
</details>

### Held text, Walden / Reading / paragraphs 4-5

```
However much we may admire the orator's occasional bursts of eloquence, the
noblest written words are commonly as far behind or above the fleeting
spoken language as the firmament with its stars is behind the clouds.
_There_ are the stars, and they who can may read them. The astronomers
forever comment on and observe them. They are not exhalations like our daily
colloquies and vaporous breath. What is called eloquence in the forum is
commonly found to be rhetoric in the study. The orator yields to the
inspiration of a transient occasion, and speaks to the mob before him, to
those who can _hear_ him; but the writer, whose more equable life is his
occasion, and who would be distracted by the event and the crowd which
inspire the orator, speaks to the intellect and health of mankind, to all in
any age who can _understand_ him. No wonder that Alexander carried the Iliad
with him on his expeditions in a precious casket. A written word is the
choicest of relics. It is something at once more intimate with us and more
universal than any other work of art. It is the work of art nearest to life
itself. It may be translated into every language, and not only be read but
actually breathed from all human lips;—not be represented on canvas or in
marble only, but be carved out of the breath of life itself. The symbol of
an ancient man's thought becomes a modern man's speech. Two thousand summers
have imparted to the monuments of Grecian literature, as to her marbles,
only a maturer golden and autumnal tint, for they have carried their own
serene and celestial atmosphere into all lands to protect them against the
corrosion of time. Books are the treasured wealth of the world and the fit
inheritance of generations and nations. Books, the oldest and the best,
stand naturally and rightfully on the shelves of every cottage. They have no
cause of their own to plead, but while they enlighten and sustain the reader
his common sense will not refuse them. Their authors are a natural and
irresistible aristocracy in every society, and, more than kings or emperors,
exert an influence on mankind. When the illiterate and perhaps scornful
trader has earned by enterprise and industry his coveted leisure and
independence, and is admitted to the circles of wealth and fashion, he turns
inevitably at last to those still higher but yet inaccessible circles of
intellect and genius, and is sensible only of the imperfection of his
culture and the vanity and insufficiency of all his riches, and further
proves his good sense by the pains which he takes to secure for his children
that intellectual culture whose want he so keenly feels; and thus it is that
he becomes the founder of a family.
```

**Verdict:** 

---

## 6. `src-000390-p1/Walden`

- Footnote: `[_Walden_, p. 139; Riv. 197.]`
- Key says: **Walden / Sounds / paragraphs 23-26**
- Anchors: `src-000729-p23` … `src-000729-p26`
- Edition cross-check: Riverside p. 197, residual -0.09 pages

**Look for these, in the span below:**

- opens: `Lincoln woods. I was also serenaded by a hooting owl. Near at`
- closes: `to express the meaning of Nature there. Late in the evening I`

<details>
<summary>Manuscript Edition page 139, as scanned (296 words)</summary>

```
Lincoln woods. I was also serenaded by a hooting owl. Near at hand you could
fancy it the most melancholy sound in Nature, as if she meant by this to
stereotype and make perma- nent in her choir the dying moans of a human
being, — some poor weak relic of mortality who has left hope be- SOUNDS 139
hind, and howls like an animal, yet with human sobs, on entering the dark
valley, made more awful by a cer- tain gurgling melodiousness, — I find
myself beginning with the letters gl when I try to imitate it, — expressive
of a mind which has reached the gelatinous, mildewy stage in the
mortification of all healthy and courageous thought. It reminded me of
ghouls and idiots and insane bowlings. But now one answers from far woods in
a strain made really melodious by distance, — Hoo hoo hoo, hoorer hoo; and
indeed for the most part it sug- gested only pleasing associations, whether
heard by day or night, summer or winter. I rejoice that there are owls. Let
them do the idiotic and maniacal hooting for men. It is a sound admirably
suited to swamps and twilight woods which no day il- lustrates, suggesting a
vast and undeveloped nature which men have not recognized. They represent
the stark twilight and unsatisfied thoughts which all have. All day the sun
has shone on the surface of some savage swamp, where the single spruce
stands hung with usnea lichens, and small hawks circulate above, and the
chick- adee lisps amid the evergreens, and the partridge and rabbit skulk
beneath ; but now a more dismal and fitting day dawns, and a different race
of creatures awakes to express the meaning of Nature there. Late in the
evening I
```
</details>

### Held text, Walden / Sounds / paragraphs 23-26

```
When other birds are still the screech owls take up the strain, like
mourning women their ancient u-lu-lu. Their dismal scream is truly Ben
Jonsonian. Wise midnight hags! It is no honest and blunt tu-whit tu-who of
the poets, but, without jesting, a most solemn graveyard ditty, the mutual
consolations of suicide lovers remembering the pangs and the delights of
supernal love in the infernal groves. Yet I love to hear their wailing,
their doleful responses, trilled along the wood-side; reminding me sometimes
of music and singing birds; as if it were the dark and tearful side of
music, the regrets and sighs that would fain be sung. They are the spirits,
the low spirits and melancholy forebodings, of fallen souls that once in
human shape night-walked the earth and did the deeds of darkness, now
expiating their sins with their wailing hymns or threnodies in the scenery
of their transgressions. They give me a new sense of the variety and
capacity of that nature which is our common dwelling. _Oh-o-o-o-o that I
never had been bor-r-r-r-n!_ sighs one on this side of the pond, and circles
with the restlessness of despair to some new perch on the gray oaks.
Then—_that I never had been bor-r-r-r-n!_ echoes another on the farther side
with tremulous sincerity, and—_bor-r-r-r-n!_ comes faintly from far in the
Lincoln woods. I was also serenaded by a hooting owl. Near at hand you could
fancy it the most melancholy sound in Nature, as if she meant by this to
stereotype and make permanent in her choir the dying moans of a human
being,—some poor weak relic of mortality who has left hope behind, and howls
like an animal, yet with human sobs, on entering the dark valley, made more
awful by a certain gurgling melodiousness,—I find myself beginning with the
letters gl when I try to imitate it,—expressive of a mind which has reached
the gelatinous mildewy stage in the mortification of all healthy and
courageous thought. It reminded me of ghouls and idiots and insane howlings.
But now one answers from far woods in a strain made really melodious by
distance,—_Hoo hoo hoo, hoorer hoo_; and indeed for the most part it
suggested only pleasing associations, whether heard by day or night, summer
or winter. I rejoice that there are owls. Let them do the idiotic and
maniacal hooting for men. It is a sound admirably suited to swamps and
twilight woods which no day illustrates, suggesting a vast and undeveloped
nature which men have not recognized. They represent the stark twilight and
unsatisfied thoughts which all have. All day the sun has shone on the
surface of some savage swamp, where the single spruce stands hung with usnea
lichens, and small hawks circulate above, and the chickadee lisps amid the
evergreens, and the partridge and rabbit skulk beneath; but now a more
dismal and fitting day dawns, and a different race of creatures awakes to
express the meaning of Nature there. Late in the evening I heard the distant
rumbling of wagons over bridges,—a sound heard farther than almost any other
at night,—the baying of dogs, and sometimes again the lowing of some
disconsolate cow in a distant barn-yard. In the mean while all the shore
rang with the trump of bullfrogs, the sturdy spirits of ancient wine-bibbers
and wassailers, still unrepentant, trying to sing a catch in their Stygian
lake,—if the Walden nymphs will pardon the comparison, for though there are
almost no weeds, there are frogs there,—who would fain keep up the hilarious
rules of their old festal tables, though their voices have waxed hoarse and
solemnly grave, mocking at mirth, and the wine has lost its flavor, and
become only liquor to distend their paunches, and sweet intoxication never
comes to drown the memory of the past, but mere saturation and
waterloggedness and distention. The most aldermanic, with his chin upon a
heart-leaf, which serves for a napkin to his drooling chaps, under this
northern shore quaffs a deep draught of the once scorned water, and passes
round the cup with the ejaculation _tr-r-r-oonk, tr-r-r-oonk, tr-r-r-oonk!_
and straightway comes over the water from some distant cove the same
password repeated, where the next in seniority and girth has gulped down to
his mark; and when this observance has made the circuit of the shores, then
ejaculates the master of ceremonies, with satisfaction, _tr-r-r-oonk!_ and
each in his turn repeats the same down to the least distended, leakiest, and
flabbiest paunched, that there be no mistake; and then the bowl goes round
again and again, until the sun disperses the morning mist, and only the
patriarch is not under the pond, but vainly bellowing _troonk_ from time to
time, and pausing for a reply.
```

**Verdict:** 

---
