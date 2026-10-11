PRAGMA user_version=1;
CREATE TABLE orders(tenant TEXT NOT NULL,id TEXT NOT NULL,status TEXT NOT NULL,currency TEXT NOT NULL,total_cents INTEGER NOT NULL,customer TEXT NOT NULL,PRIMARY KEY(tenant,id));
CREATE TABLE order_items(tenant TEXT NOT NULL,order_id TEXT NOT NULL,sku TEXT NOT NULL,quantity INTEGER NOT NULL,paid_cents INTEGER NOT NULL,PRIMARY KEY(tenant,order_id,sku));
CREATE TABLE inventory(tenant TEXT NOT NULL,sku TEXT NOT NULL,on_hand INTEGER NOT NULL,PRIMARY KEY(tenant,sku));
INSERT INTO orders VALUES('alpha','o1','paid','PLN',1000,'alice'),('alpha','unpaid','pending','PLN',100,'alice'),('beta','o1','paid','PLN',1000,'bob');
INSERT INTO order_items VALUES('alpha','o1','book',3,1000),('alpha','unpaid','book',1,100),('beta','o1','book',3,1000);
INSERT INTO inventory VALUES('alpha','book',10),('beta','book',20);
